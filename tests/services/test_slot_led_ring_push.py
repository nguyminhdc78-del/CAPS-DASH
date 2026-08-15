"""The bay-status ring: what gets pushed, how often, and when it gives up.

No hardware. An `httpx.MockTransport` stands in for the ESP32, so what is
under test is the encoding and the three rules that let this run inside a
camera loop - throttling, silence on failure, and self-disabling against a
device that has no ring.
"""

from __future__ import annotations

import httpx
import pytest

from caps_dash.services import slot_led_service
from caps_dash.services.slot_led_service import REFRESH_S, SlotLedRing, encode_states
from caps_dash.vision.domain import SlotState

ESP32 = {"source_type": "esp32cam_http", "source_url": "http://192.0.2.10/anh", "code": "01"}


@pytest.fixture
def device(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every `slots` value the device is sent. Answers 200."""
    return _stub_device(monkeypatch, httpx.Response(200, json={"ok": True}))


def _stub_device(
    monkeypatch: pytest.MonkeyPatch, response: httpx.Response | Exception
) -> list[str]:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ring"
        seen.append(request.url.params["slots"])
        if isinstance(response, Exception):
            raise response
        return response

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def patched(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(slot_led_service.httpx, "AsyncClient", patched)
    return seen


def test_encoding_is_ordered_by_bay_code_not_by_dict_order() -> None:
    # The arcs are physical positions on the ring. A bay that moved because a
    # dict was built differently would relabel the lamp silently.
    states = {"A3": SlotState.UNKNOWN, "A1": SlotState.OCCUPIED, "A2": SlotState.FREE}

    assert encode_states(states) == "10u"


def test_unknown_never_encodes_as_free() -> None:
    # The hard rule of the whole system, on the lamp: green sends a driver to
    # a space nobody has actually looked at.
    assert encode_states({"A1": SlotState.UNKNOWN}) == "u"


@pytest.mark.asyncio
async def test_pushes_once_then_stays_quiet_until_the_state_changes(device: list[str]) -> None:
    ring = SlotLedRing()

    await ring.push(states={"A1": SlotState.FREE}, **ESP32)
    await ring.push(states={"A1": SlotState.FREE}, **ESP32)
    await ring.push(states={"A1": SlotState.OCCUPIED}, **ESP32)

    assert device == ["0", "1"]


@pytest.mark.asyncio
async def test_refreshes_an_unchanged_state_so_a_rebooted_ring_repairs_itself(
    device: list[str],
) -> None:
    ring = SlotLedRing()
    await ring.push(states={"A1": SlotState.OCCUPIED}, **ESP32)

    ring.last_sent_at -= REFRESH_S + 1.0
    await ring.push(states={"A1": SlotState.OCCUPIED}, **ESP32)

    assert device == ["1", "1"]


@pytest.mark.asyncio
async def test_a_device_without_a_ring_is_asked_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The reference rig is a MaixCam typed `esp32cam_http`. One 404 answers
    # "does this have a ring?" for good, rather than logging a failure every
    # fifteen seconds forever.
    seen = _stub_device(monkeypatch, httpx.Response(404))
    ring = SlotLedRing()

    await ring.push(states={"A1": SlotState.FREE}, **ESP32)
    await ring.push(states={"A1": SlotState.OCCUPIED}, **ESP32)

    assert seen == ["0"]
    assert ring.supported is False


@pytest.mark.asyncio
async def test_an_unreachable_device_is_swallowed_and_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A lamp problem is never a detection problem: this runs on the detector's
    # task, so it must not raise - and unlike a 404, a connect error is
    # transient and worth trying again.
    seen = _stub_device(monkeypatch, httpx.ConnectError("no route to host"))
    ring = SlotLedRing()

    await ring.push(states={"A1": SlotState.FREE}, **ESP32)
    await ring.push(states={"A1": SlotState.FREE}, **ESP32)

    assert seen == ["0", "0"]
    assert ring.supported is True
    assert ring.last_payload == ""


@pytest.mark.asyncio
async def test_sources_that_cannot_have_a_ring_are_never_contacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _stub_device(monkeypatch, httpx.Response(200))
    ring = SlotLedRing()

    await ring.push(
        source_type="image_folder",
        source_url="/var/lib/caps/frames",
        code="99",
        states={"A1": SlotState.FREE},
    )

    assert seen == []
    assert ring.supported is False


@pytest.mark.asyncio
async def test_more_bays_than_the_ring_can_divide_is_refused_here(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Nine one-LED arcs mean nothing from across a car park, and the firmware
    # answers 400. Catch it here rather than retrying into that forever.
    seen = _stub_device(monkeypatch, httpx.Response(200))
    ring = SlotLedRing()

    await ring.push(states={f"A{i}": SlotState.FREE for i in range(9)}, **ESP32)

    assert seen == []
    assert ring.supported is False

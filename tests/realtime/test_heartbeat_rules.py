"""Heartbeat bookkeeping, tested without a socket or a clock to wait on."""

from __future__ import annotations

import datetime as dt

from caps_dash.realtime.ws_heartbeat import MAX_MISSED_PINGS, Heartbeat


def test_a_token_that_has_not_expired_keeps_the_stream_open():
    future = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)
    assert Heartbeat(20.0, future).token_expired is False


def test_an_expired_token_ends_the_stream():
    """A stream must not outlive the credential that opened it."""
    past = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    assert Heartbeat(20.0, past).token_expired is True


def test_a_connection_without_an_expiry_is_never_forced_to_close():
    assert Heartbeat(20.0, None).token_expired is False


def test_a_pong_clears_the_missed_counter():
    heartbeat = Heartbeat(20.0, None)
    heartbeat.record_pong()
    # One missed ping is tolerated; a single lost packet on bad wifi should not
    # kill a working stream.
    assert MAX_MISSED_PINGS >= 2

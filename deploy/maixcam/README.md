# MaixCam HTTP snapshot app

The camera (`maixcam-1677`, riscv64, GC4653 sensor) serves one JPEG per
`GET /snapshot` on port 8080. The backend polls it every 2.0 s through
`Esp32CamHttpSource` — the same source type an ESP32-CAM uses, because the
contract is the same: one still per request.

**Reach it over WiFi**, not USB-C. Measured 2026-08-12: `usb0` exists and holds
`10.22.120.1` but is NO-CARRIER/DOWN — the USB-C cable supplies power only. The
camera joins the hotspot and takes a DHCP address (`192.168.137.90` on the
day). Because that moves, find it from the hotspot's client list, or probe:

```bash
ssh -i ~/.ssh/maixcam root@<ip> hostname   # answers maixcam-1677
```

The device is small: **1 CPU core, 128 MB RAM, CPython 3.11.6, no systemd.**
Every constant in `http_snapshot_main.py` is sized for that.

**Status: installed and running as of 2026-08-12.** The app is at
`/maixapp/apps/http_snapshot/`, `auto_start.txt` points at it, and the UNO Q
polls it every 2.0 s with zero read failures. Full measurements:
`plans/260812-1757-snapshot-polling-replaces-rtsp-stream/reports/phase-01-spike-measurements.md`.

**Not yet proven: the power cycle.** Autostart is configured, not demonstrated.
Reboot and confirm `/snapshot` answers unattended before trusting it.

## Files

| Repo | Device |
|---|---|
| `http_snapshot_main.py` | `/maixapp/apps/http_snapshot/main.py` |
| `app.yaml` | `/maixapp/apps/http_snapshot/app.yaml` |

The repo copy is the source of truth. Edit here, then copy — not the reverse.

## What it does

A daemon thread opens the sensor once and keeps the newest JPEG in one `bytes`
slot; the HTTP handler serves whatever is in that slot. Capture runs at 2 fps
against a 0.5 Hz poll, so a `GET` never waits for a capture.

- `GET /snapshot` → `200 image/jpeg` with an exact `Content-Length`
- before the first frame → `503`
- frame older than `MAX_FRAME_AGE_S` (10 s) → `503`
- anything else → `404`

Holding the sensor open is not an optimisation. Measured on this device:
opening it costs **1034 ms**, and the first frame back is unconverged — 5.4 KB
of flat grey against ~37 KB once AE/AWB settle. Capture-on-request would serve
that frame every time.

## What the screen shows

The device paints the live picture with the port, the addresses it is reachable
on, and two counters:

```
HTTP snapshot :8080
192.168.137.90
                                    frames 109  served 7
```

`frames` is what the capture thread has produced; **`served` is what the
backend has actually collected**, which is the more useful of the two — it
separates "this app is alive" from "the dashboard is really polling it".

This exists because the first version drew nothing at all, so the screen kept
showing whatever the launcher last painted. A working camera then looked
identical, to anyone standing in front of it, to one that hung at boot — and it
was reported as "stuck on the waiting screen" twice while it was serving frames
the whole time. Drawing is best-effort and wrapped: a board with no display
keeps serving.

The overlay is drawn **after** the JPEG is encoded, so the frame the backend
receives never carries it.

The staleness guard is the other part worth understanding. If the capture
thread dies, the cache holds the last good picture forever. Without the guard
the server answers `200` with it, the backend decodes a valid JPEG, and the
camera is reported healthy while showing a frozen scene — a failure with no
symptom. With it: `503` → `raise_for_status()` → `_fail()` → `fail_streak` →
offline alert after 3 consecutive failures.

## Security posture

The endpoint has **no authentication and no TLS, and it is on WiFi.**

The original plan justified the missing auth by the link being point-to-point
USB-C. That justification did not survive measurement — the camera is on the
same WPA2 hotspot as the board, so **anyone with the hotspot password can fetch
a live camera frame.** Today that is bounded by the hotspot carrying two
devices and being run by the camera's owner, but it is bounded by a password,
not by topology.

`BIND_HOST` is `0.0.0.0` and must be: the DHCP address moves, and binding a
stale one would *succeed* against a down interface and serve nobody. Instead
the app prints every address it landed on at startup, so the exposure is seen
rather than assumed:

```
listening on 0.0.0.0:8080 - NO AUTHENTICATION
  http://192.168.137.90:8080/snapshot
```

**Before moving this camera to a shared or larger network, put authentication
in front of it.** Do not treat the current posture as a default that travels.

## Install

```bash
CAM=root@<camera-ip>
K=~/.ssh/maixcam

# 1. Stop whatever owns the sensor. Verified working 2026-08-12; the launcher
#    does not restart it. Not optional: a second process CAN open the camera
#    and then fails on read with "Value is NULL: camera read failed".
ssh -i $K $CAM 'killall -q python3'

# 2. Record what autostarts today, so rollback has a target. It was
#    `rtmp_live` here, NOT `rtsp_stream`.
ssh -i $K $CAM 'cp /maixapp/auto_start.txt /root/auto_start.txt.bak; cat /root/auto_start.txt.bak'

# 3. Copy the app.
ssh -i $K $CAM 'mkdir -p /maixapp/apps/http_snapshot'
scp -i $K http_snapshot_main.py $CAM:/maixapp/apps/http_snapshot/main.py
scp -i $K app.yaml              $CAM:/maixapp/apps/http_snapshot/app.yaml

# 4. Autostart. This board has NO systemd (checked), so `auto_start.txt` — one
#    line, the app id — is the mechanism. It does not restart on crash.
ssh -i $K $CAM 'echo -n http_snapshot > /maixapp/auto_start.txt'

# 5. Start it now without waiting for a reboot.
ssh -i $K $CAM 'cd /maixapp/apps/http_snapshot && nohup python3 main.py > /tmp/http_snapshot.log 2>&1 &'
```

### Smoke test

```bash
curl -v http://<camera-ip>:8080/snapshot -o frame.jpg      # 200, Content-Length == file size
curl -s -o /dev/null -w '%{http_code}\n' http://<camera-ip>:8080/   # 404
```

Measured on install day: `200`, **35702 bytes**, 54 ms, decodes as 640×480.

### Latency, from the board — this is the number that matters

Run it from the UNO Q, not the laptop: the board is the consumer, and it uses
`httpx` with keep-alive, which is what the 2 s idle gap tests.

```bash
cd /home/arduino/caps-dash && .venv/bin/python - <<'EOF'
import httpx, time, statistics
c = httpx.Client(timeout=httpx.Timeout(8.0))
lat = []
for _ in range(20):
    t = time.perf_counter(); c.get('http://<camera-ip>:8080/snapshot')
    lat.append((time.perf_counter() - t) * 1000); time.sleep(2.0)
lat.sort()
print(f'min={lat[0]:.0f} mean={statistics.mean(lat):.0f} p90={lat[17]:.0f} max={lat[-1]:.0f}')
EOF
```

Measured: **min 45 / mean 68 / p90 75 / max 134 ms**, bodies 35.1–35.9 KB.

**Do not derive `CAMERA_TIMEOUT_S` from p90 × 3 here.** That rule gives 0.23 s,
which is far too tight for a link that has shown 251 ms spikes. A timeout
guards a *wedged* server, not a slow one. Leave it at 5.0 (8.0 on the board)
and let `CAMERA_FAIL_STREAK_OFFLINE=3` do the offline detection.

The two guards catch different faults and neither replaces the other. A dead
*capture thread* is caught by the staleness guard, which answers `503`
immediately — the timeout would never fire, because the HTTP server is still
perfectly responsive. `CAMERA_TIMEOUT_S` catches the server never answering.

## What a 503 tells you

The capture thread is a daemon, so if it dies the HTTP server keeps serving.
Rather than leave every failure looking like "no frame captured yet", the
thread records why it stopped and the 503 body says so:

| body | meaning |
|---|---|
| `no frame captured yet` | Healthy, in its first second. Also what you see while `open_camera()` is still waiting for the sensor — check stderr for `camera open failed`. |
| `no encode path on this firmware yields JPEG bytes` | The startup probe tried all three paths and none produced JPEG. Needs a code change, not a retry. |
| `capture thread stopped: ...` | The thread died. Exception type and message are in the body. |
| `stale frame: N.Ns old` | The thread is alive but has produced nothing for `MAX_FRAME_AGE_S`. |

A persistent capture failure re-opens the camera after
`CAPTURE_FAILS_BEFORE_REOPEN` consecutive errors, so a sensor that goes away
and comes back recovers unattended instead of needing a power cycle.

**Dropped connections are silent by design.** `socketserver` prints a full
traceback for any exception escaping a handler thread, and a client that
vanishes mid-keep-alive raises `ConnectionResetError` there — which is not a
fault, it is the backend restarting. Measured: one backend restart wrote two
~15-line tracebacks to flash. `QuietThreadingHTTPServer.handle_error` drops
connection and timeout errors and prints everything else, so if you *do* see a
traceback from this app, it is worth reading.

## Encode path

`main.py` does not assume how the firmware encodes JPEG. At startup it tries
`to_jpeg().to_bytes()`, then `compress(85).to_bytes()`, then `to_bytes()`, and
keeps the first whose output starts with `ff d8 ff`, printing which won.

Measured on this firmware — **`to_jpeg` wins**, and the fallback chain earns
its place by correctly rejecting the third:

| candidate | result |
|---|---|
| `to_jpeg().to_bytes()` | `bytes`, JPEG magic ✅ |
| `compress(85).to_bytes()` | also JPEG |
| `to_bytes()` | 921600 B — raw 640×480×3 pixels, rejected |

JPEG size across 10 frames: 35574 / 37379 / 41453 B (min/mean/max) — roughly
70× above `MIN_BODY_BYTES` and 48× below `MAX_BODY_BYTES`.

## Rollback

`/maixapp/apps/rtsp_stream/main.py` is untouched by this install (still dated
2024-09-05), and the previous autostart target is saved at
`/root/auto_start.txt.bak`. Restore whichever you want:

```bash
# Back to what was running before this app (was `rtmp_live`):
ssh -i ~/.ssh/maixcam root@<camera-ip> 'cp /root/auto_start.txt.bak /maixapp/auto_start.txt'
# ...or to the RTSP streamer:
ssh -i ~/.ssh/maixcam root@<camera-ip> 'echo -n rtsp_stream > /maixapp/auto_start.txt'
ssh -i ~/.ssh/maixcam root@<camera-ip> reboot
```

Then point the camera row's `source_type` back to `rtsp` in the dashboard and
set its `source_url` to `rtsp://<camera-ip>:8554/live`. `RtspStreamSource` and
its tests are still in the codebase — RTSP was demoted, not removed.

**This path has never been rehearsed** (accepted deliberately; see the plan's
Validation Log, session 1). Reboot is the guaranteed reset if it misbehaves.

## Tuning

| Constant | Default | Note |
|---|---|---|
| `CAPTURE_FPS` | 2.0 | **Not a CPU lever.** Measured: 2.0 fps → 53–55% app CPU, 0.5 fps → 53–54%. Four times fewer captures, same CPU — the cost is holding the sensor open, since the ISP runs at the sensor's own rate regardless. So this buys freshness only: 2 fps leaves a `GET` at most 500 ms stale, below the WiFi jitter. If the camera's CPU ever matters, change the *sensor's* configuration. |
| `DISPLAY_EVERY_N_FRAMES` | 1 | Draw the status screen on every captured frame. Costs ~1–3 points of CPU on top of the 53% floor. Raise it to draw less often; the screen is the only way to judge the device by looking at it. |
| `MAX_FRAME_AGE_S` | 10.0 | 5× the poll interval. Raise only with the poll interval. |
| `BIND_HOST` | `0.0.0.0` | Read the security section before changing. |
| `PORT` | 8080 | Matches the camera row's `source_url`. |
| `CAPTURE_FAILS_BEFORE_REOPEN` | 10 | ~7 s of failures before the sensor handle is assumed dead. |
| `Handler.timeout` | 30 | Bounds an idle keep-alive connection. Without it, a link that drops without a FIN parks a server thread forever. |

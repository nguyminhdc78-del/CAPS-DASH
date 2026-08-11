# Models

The vehicle detector runs from `yolo-vehicle.onnx` in this directory.

## Why the `.onnx` is committed

Clone-and-run must work with no network. This matters twice: at a competition
demo, and when flashing an Arduino UNO Q that may have no internet on site.
A few megabytes in git history is a cheaper problem than a build that fails
because a download host was unreachable.

Training checkpoints (`.pt`, `.pth`) are **not** committed — see `.gitignore`.

## Why ONNX and not Ultralytics at runtime

Ultralytics is **AGPL-3.0**. This project's source is published as a condition
of the competition, and an AGPL runtime dependency reaches further than the
team intends. `onnxruntime` is Apache-2.0.

Ultralytics stays available as the `vision-dev` optional extra, used on a
developer machine for one job only: exporting the `.onnx`. It must never
appear in the deployed dependency set.

## Re-exporting the model

On a development machine (not the board):

```bash
pip install -e ".[vision-dev]"
python -m caps_dash.vision.export_onnx --weights yolo11n.pt --out models/yolo-vehicle.onnx
```

Record what was exported below whenever it changes.

| Date | Source weights | Input size | Notes |
|---|---|---|---|
| _pending_ | — | 640 | Placeholder until the first export |

## Runtime notes for the target board

`onnxruntime` publishes a `manylinux_2_28_aarch64` wheel for CPython 3.12, so
the Arduino UNO Q (QRB2210, aarch64) is supported — provided its distribution
ships **glibc 2.28 or newer** (Debian 10+). Verify this before deploying.

CPU is the baseline execution provider. Any accelerator path on this SoC is
unverified and must stay behind a configuration flag. Note that the Hexagon
DSP on the QRB2210 targets sensor fusion and audio, not vision — it is not an
NPU for this workload.

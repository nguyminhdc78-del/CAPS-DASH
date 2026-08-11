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
python -m caps_dash.vision.export_onnx --weights yolo26n.pt
```

Record what was exported below whenever it changes.

| Date | Source weights | Input size | Notes |
|---|---|---|---|
| 2026-08-12 | yolo26n.pt (ultralytics 8.4.117) | 640 | End-to-end head, `[1, 300, 6]` |

## Head layout, and why it is worth writing down

YOLO26 exports an **end-to-end** head: `[1, 300, 6]` of
`(x1, y1, x2, y2, score, class_id)`, with NMS already applied inside the
graph. YOLOv8 and YOLO11 export the classic `[1, 4 + num_classes, N]` of
cxcywh boxes and per-class scores, NMS still to run.

`detectors/onnx_decode.py` handles both and picks by row width. Getting this
wrong does not raise: the classic path reads columns 4 and 5 of an end-to-end
row as two class scores, so a class id of 59 is read as a confidence of 59.0
and every frame decodes to nothing. If you export a different model family,
check the printed `output_shape` in the `onnx_session_loaded` log line against
what the decoder expects.

## Runtime notes for the target board

`onnxruntime` publishes a `manylinux_2_28_aarch64` wheel for CPython 3.12, so
the Arduino UNO Q (QRB2210, aarch64) is supported — provided its distribution
ships **glibc 2.28 or newer** (Debian 10+). Verify this before deploying.

CPU is the baseline execution provider. Any accelerator path on this SoC is
unverified and must stay behind a configuration flag. Note that the Hexagon
DSP on the QRB2210 targets sensor fusion and audio, not vision — it is not an
NPU for this workload.

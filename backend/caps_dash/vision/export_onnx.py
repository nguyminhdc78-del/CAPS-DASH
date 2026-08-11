"""Export a YOLO checkpoint to the ONNX file the runtime detector loads.

Runs on a development machine, never on the board. This is the only place
`ultralytics` is imported anywhere in the project: it is AGPL-3.0, so it lives
in the `vision-dev` optional extra and must never enter the deployed
dependency set. The import is inside the function for exactly that reason -
importing this module must not require the package unless an export is
actually being run.

    pip install -e ".[vision-dev]"
    python -m caps_dash.vision.export_onnx --weights yolo26n.pt

The weights file is downloaded by ultralytics on first use if it is not
already on disk.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = REPO_ROOT / "models" / "yolo-vehicle.onnx"

# Must match `Settings.inference_input_size`. The ONNX graph is exported with a
# fixed input resolution, so a mismatch here does not fail loudly - it feeds
# the detector letterboxed frames at the wrong scale and quietly degrades
# every detection.
DEFAULT_INPUT_SIZE = 640

# COCO class ids the car park cares about. Kept here as documentation of what
# the exported model is expected to emit; filtering happens at runtime in
# `detectors/onnx_decode.py`, not in the graph.
VEHICLE_CLASS_IDS = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="export_onnx", description="Export YOLO weights to ONNX for CAPS-DASH"
    )
    parser.add_argument(
        "--weights",
        default="yolo26n.pt",
        help="Checkpoint to export. Downloaded on first use if absent.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--input-size", type=int, default=DEFAULT_INPUT_SIZE)
    parser.add_argument(
        "--opset",
        type=int,
        default=None,
        help="ONNX opset. Left to ultralytics' default unless given.",
    )
    parser.add_argument(
        "--simplify",
        action="store_true",
        help="Run onnxsim on the graph. Smaller and faster, but needs onnxsim installed.",
    )
    return parser


def export(
    *,
    weights: str,
    out: Path,
    input_size: int = DEFAULT_INPUT_SIZE,
    opset: int | None = None,
    simplify: bool = False,
) -> Path:
    """Export `weights` to `out` and return the path actually written."""
    from ultralytics import YOLO  # type: ignore[attr-defined]

    model = YOLO(weights)
    kwargs: dict[str, object] = {
        "format": "onnx",
        "imgsz": input_size,
        "simplify": simplify,
        # The board runs CPU inference, and a dynamic batch axis buys nothing
        # for a one-frame-at-a-time pipeline while making some runtimes slower.
        "dynamic": False,
        "batch": 1,
    }
    if opset is not None:
        kwargs["opset"] = opset

    produced = Path(model.export(**kwargs))

    out.parent.mkdir(parents=True, exist_ok=True)
    if produced.resolve() != out.resolve():
        # ultralytics writes next to the checkpoint; move it where the runtime
        # actually looks (`Settings.model_path`).
        shutil.move(str(produced), out)
    return out


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    written = export(
        weights=args.weights,
        out=args.out,
        input_size=args.input_size,
        opset=args.opset,
        simplify=args.simplify,
    )
    size_mb = written.stat().st_size / (1024 * 1024)

    print(f"wrote {written} ({size_mb:.1f} MB) from {args.weights} at {args.input_size}px")
    print("Record this export in models/README.md, then verify with:")
    print('  python -c "import onnxruntime as ort;'
          f' print(ort.InferenceSession(r\'{written}\').get_inputs()[0])"')
    return 0


if __name__ == "__main__":
    sys.exit(main())

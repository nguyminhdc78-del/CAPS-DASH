"""Tuning constants for the ONNX/Ultralytics detection backends.

Fixed by the model and the problem rather than by preference, so they live
beside the code that uses them rather than in application settings - the same
reasoning as `vision/domain/constants.py`.
"""

from __future__ import annotations

# Runtime-mutable confidence (see `VehicleDetector.confidence`) is clamped
# into this range. Below 0.01 is pure noise; above 0.95 a real vehicle under
# normal lighting can never clear the bar, which silently blinds the camera.
MIN_CONFIDENCE = 0.01
MAX_CONFIDENCE = 0.95

# COCO class ids CAPS cares about. The exported model is a stock
# COCO-pretrained YOLO (80 classes); CAPS only tracks vehicles parked in a
# slot, so everything else (person, bicycle, chair, ...) is filtered at
# decode time rather than by retraining the model.
VEHICLE_CLASS_LABELS: dict[int, str] = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

# Width of an end-to-end (NMS-free) head row: x1, y1, x2, y2, score, class_id.
# A classic YOLO head is 4 + num_classes wide, and this project ships a stock
# 80-class COCO model, so 84 - six columns can only mean the end-to-end
# layout. Retraining to exactly two classes would make this ambiguous; if that
# ever happens, the decoder needs an explicit setting rather than a guess.
END_TO_END_COLUMNS = 6

# Per-class NMS IoU threshold. 0.45 is the common YOLO default: two boxes
# overlapping more than this are almost certainly the same vehicle counted
# twice, not two vehicles parked touching each other.
NMS_IOU_THRESHOLD = 0.45

# Cap candidate boxes before NMS runs. NMS is O(n^2); on a frame full of
# false positives before confidence filtering this bounds the worst case on
# the aarch64 board rather than letting one bad frame stall the pipeline.
MAX_CANDIDATES_BEFORE_NMS = 100

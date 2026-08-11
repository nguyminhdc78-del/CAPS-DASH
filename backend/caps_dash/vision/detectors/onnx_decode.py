"""Decodes a raw ONNX YOLO head output into `Detection` objects.

TWO HEAD LAYOUTS, and telling them apart matters more than it looks.

**Classic** (YOLOv8 / YOLO11): `[1, 4 + num_classes, N]` - channels before
anchors - or already `[1, N, 4 + num_classes]`. Boxes are `cxcywh`, every
class carries its own score, and NMS has *not* run. That is the layout
`_decode_classic` handles.

**End-to-end** (YOLO26): `[1, 300, 6]` = `(x1, y1, x2, y2, score, class_id)`,
already in `xyxy`, already NMS'd inside the graph - YOLO26 removed NMS from
the pipeline entirely. Feeding this to the classic path does not raise: it
slices columns 4 and 5 as if they were two class scores, so `argmax` reads a
class id of `59` as a confidence of 59.0 and the frame decodes to nonsense.
Nothing anywhere would report an error; the car park would simply stop seeing
cars. Hence the explicit width check below rather than a best-effort guess.
"""

from __future__ import annotations

import numpy as np

from ..domain import Detection
from .box_utils import nms, unletterbox_boxes
from .constants import (
    END_TO_END_COLUMNS,
    MAX_CANDIDATES_BEFORE_NMS,
    NMS_IOU_THRESHOLD,
    VEHICLE_CLASS_LABELS,
)


def decode_yolo_output(
    raw_output: np.ndarray,
    scale: float,
    pad: tuple[float, float],
    orig_w: int,
    orig_h: int,
    confidence: float,
) -> list[Detection]:
    """Raw session output -> filtered, NMS'd, original-pixel `Detection` list."""
    predictions = _to_rows(raw_output)
    # Both axes must be checked. A head with zero anchors keeps its channel
    # count, so a row-count test alone passes it through to argmax, which
    # raises on an empty sequence. Some exports (NMS baked into the graph)
    # legitimately return nothing at all on a quiet frame.
    if predictions.shape[0] == 0 or predictions.shape[1] <= 4:
        return []

    if predictions.shape[1] == END_TO_END_COLUMNS:
        return _decode_end_to_end(predictions, scale, pad, orig_w, orig_h, confidence)
    return _decode_classic(predictions, scale, pad, orig_w, orig_h, confidence)


def _decode_classic(
    predictions: np.ndarray,
    scale: float,
    pad: tuple[float, float],
    orig_w: int,
    orig_h: int,
    confidence: float,
) -> list[Detection]:
    """`(N, 4 + num_classes)`: cxcywh boxes, per-class scores, NMS still to run."""
    class_scores = predictions[:, 4:]
    class_ids = class_scores.argmax(axis=1)
    scores = class_scores.max(axis=1)

    vehicle_ids = np.fromiter(VEHICLE_CLASS_LABELS, dtype=class_ids.dtype)
    keep_mask = (scores >= confidence) & np.isin(class_ids, vehicle_ids)
    if not keep_mask.any():
        return []

    boxes_cxcywh = predictions[keep_mask, :4]
    scores = scores[keep_mask]
    class_ids = class_ids[keep_mask]

    if boxes_cxcywh.shape[0] > MAX_CANDIDATES_BEFORE_NMS:
        top = np.argsort(scores)[::-1][:MAX_CANDIDATES_BEFORE_NMS]
        boxes_cxcywh, scores, class_ids = boxes_cxcywh[top], scores[top], class_ids[top]

    boxes_xyxy = _cxcywh_to_xyxy(boxes_cxcywh)
    keep_indices = _nms_per_class(boxes_xyxy, scores, class_ids)
    if not keep_indices:
        return []

    boxes_xyxy = unletterbox_boxes(boxes_xyxy[keep_indices], scale, pad, orig_w, orig_h)
    scores = scores[keep_indices]
    class_ids = class_ids[keep_indices]

    return [
        Detection(
            x1=float(box[0]),
            y1=float(box[1]),
            x2=float(box[2]),
            y2=float(box[3]),
            confidence=float(score),
            label=VEHICLE_CLASS_LABELS[int(class_id)],
        )
        for box, score, class_id in zip(boxes_xyxy, scores, class_ids, strict=True)
    ]


def _decode_end_to_end(
    predictions: np.ndarray,
    scale: float,
    pad: tuple[float, float],
    orig_w: int,
    orig_h: int,
    confidence: float,
) -> list[Detection]:
    """`(N, 6)`: xyxy boxes, one score, one class id, NMS already applied.

    No `argmax`, no box conversion and no NMS here - doing any of them again
    would corrupt an output that is already final. The rows are padded to a
    fixed length (300 for YOLO26), so most of them are zero-score filler that
    the confidence filter removes.
    """
    boxes_xyxy = predictions[:, :4]
    scores = predictions[:, 4]
    class_ids = predictions[:, 5].astype(np.int32)

    vehicle_ids = np.fromiter(VEHICLE_CLASS_LABELS, dtype=class_ids.dtype)
    keep_mask = (scores >= confidence) & np.isin(class_ids, vehicle_ids)
    if not keep_mask.any():
        return []

    boxes_xyxy = unletterbox_boxes(boxes_xyxy[keep_mask], scale, pad, orig_w, orig_h)
    scores = scores[keep_mask]
    class_ids = class_ids[keep_mask]

    return [
        Detection(
            x1=float(box[0]),
            y1=float(box[1]),
            x2=float(box[2]),
            y2=float(box[3]),
            confidence=float(score),
            label=VEHICLE_CLASS_LABELS[int(class_id)],
        )
        for box, score, class_id in zip(boxes_xyxy, scores, class_ids, strict=True)
    ]


def _to_rows(raw_output: np.ndarray) -> np.ndarray:
    """Normalise either head layout to one row per detection, batch dim squeezed out."""
    output = raw_output[0] if raw_output.ndim == 3 else raw_output

    # Check for the end-to-end width explicitly, before falling back to the
    # length heuristic below. That heuristic reads "shorter axis = channels",
    # which is true for a classic head (80 classes, thousands of anchors) but
    # wrong for a `(3, 6)` end-to-end output on a quiet frame - it would
    # transpose three detections into six bogus ones.
    if output.shape[1] == END_TO_END_COLUMNS:
        return output
    if output.shape[0] == END_TO_END_COLUMNS:
        return output.T

    # Classic head: `[4 + num_classes, N]` when the channel axis is shorter
    # than the anchor axis. Transpose back to one row per anchor.
    if output.shape[0] < output.shape[1]:
        output = output.T
    return output


def _cxcywh_to_xyxy(boxes: np.ndarray) -> np.ndarray:
    cx, cy, w, h = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    return np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)


def _nms_per_class(boxes: np.ndarray, scores: np.ndarray, class_ids: np.ndarray) -> list[int]:
    """NMS run separately per class, so e.g. an overlapping car and bus both survive."""
    keep: list[int] = []
    for class_id in np.unique(class_ids):
        mask = np.flatnonzero(class_ids == class_id)
        local_keep = nms(boxes[mask], scores[mask], NMS_IOU_THRESHOLD)
        keep.extend(mask[local_keep].tolist())
    return keep

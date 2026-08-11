"""Decodes a raw ONNX YOLO head output into `Detection` objects.

Head layout assumption, recorded here rather than left implicit, because an
incompatible export should fail loudly, not silently: the raw tensor is
either `[1, 4 + num_classes, N]` (channels before anchors - the common
"transposed" YOLOv8/v11 export) or already `[1, N, 4 + num_classes]`. Both
are handled by `_to_rows`; anything else means the exported model does not
match what this decoder expects.
"""

from __future__ import annotations

import numpy as np

from ..domain import Detection
from .box_utils import nms, unletterbox_boxes
from .constants import MAX_CANDIDATES_BEFORE_NMS, NMS_IOU_THRESHOLD, VEHICLE_CLASS_LABELS


def decode_yolo_output(
    raw_output: np.ndarray,
    scale: float,
    pad: tuple[float, float],
    orig_w: int,
    orig_h: int,
    confidence: float,
) -> list[Detection]:
    """Raw session output -> filtered, NMS'd, original-pixel `Detection` list."""
    predictions = _to_rows(raw_output)  # (N, 4 + num_classes): cxcywh + per-class scores
    if predictions.shape[0] == 0:
        return []

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


def _to_rows(raw_output: np.ndarray) -> np.ndarray:
    """Normalise either head layout to `(N, 4 + num_classes)`, batch dim squeezed out."""
    output = raw_output[0] if raw_output.ndim == 3 else raw_output
    # `[4 + num_classes, N]` when the channel axis is shorter than the anchor
    # axis - true for every stock YOLOv8/v11 export (80 classes, thousands of
    # anchors). Transpose back to one row per anchor.
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

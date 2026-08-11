"""Numpy geometry helpers shared by detector backends.

This is where numpy belongs - one directory over from `vision/domain`, which
must stay dependency-free. Never import this module from the domain package.
"""

from __future__ import annotations

import cv2
import numpy as np

# YOLO's conventional grey pad colour for letterboxing.
LETTERBOX_COLOR = (114, 114, 114)


def letterbox(image: np.ndarray, size: int) -> tuple[np.ndarray, float, tuple[float, float]]:
    """Resize `image` to fit inside a `size x size` square, preserving aspect ratio.

    Returns the padded square, the uniform scale factor applied, and the
    (left, top) padding added in pixels - everything `unletterbox_boxes`
    needs to map detections back to original-frame pixels. A single shared
    scale factor is correct HERE (both axes of one image resize together);
    it is only wrong when rescaling a slot polygon onto a different frame,
    which is `vision/domain/geometry.py`'s job, not this one.
    """
    height, width = image.shape[:2]
    scale = min(size / height, size / width)
    new_w, new_h = round(width * scale), round(height * scale)
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    pad_w, pad_h = size - new_w, size - new_h
    top, bottom = pad_h // 2, pad_h - pad_h // 2
    left, right = pad_w // 2, pad_w - pad_w // 2
    padded = cv2.copyMakeBorder(
        resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=LETTERBOX_COLOR
    )
    return padded, scale, (float(left), float(top))


def unletterbox_boxes(
    boxes: np.ndarray, scale: float, pad: tuple[float, float], orig_w: int, orig_h: int
) -> np.ndarray:
    """Undo `letterbox`: map xyxy boxes in padded-square pixels back to the original frame.

    `boxes` is `(N, 4)`. Padding is subtracted before the scale is undone -
    the reverse order of `letterbox`, which pads after resizing.
    """
    pad_x, pad_y = pad
    out = boxes.astype(np.float64, copy=True)
    out[:, [0, 2]] = (out[:, [0, 2]] - pad_x) / scale
    out[:, [1, 3]] = (out[:, [1, 3]] - pad_y) / scale
    out[:, [0, 2]] = np.clip(out[:, [0, 2]], 0, orig_w)
    out[:, [1, 3]] = np.clip(out[:, [1, 3]], 0, orig_h)
    return out


def nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
    """Greedy non-max suppression, pure numpy.

    Returns indices into `boxes`/`scores` to KEEP, highest score first. No
    class awareness here - callers that need per-class NMS run this once per
    class and merge the results (see `onnx_decode._nms_per_class`).
    """
    if len(boxes) == 0:
        return []

    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]

    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        rest = order[1:]

        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])

        overlap_w = np.maximum(0.0, xx2 - xx1)
        overlap_h = np.maximum(0.0, yy2 - yy1)
        intersection = overlap_w * overlap_h
        union = areas[i] + areas[rest] - intersection
        iou = np.where(union > 0, intersection / union, 0.0)

        order = rest[iou <= iou_threshold]

    return keep

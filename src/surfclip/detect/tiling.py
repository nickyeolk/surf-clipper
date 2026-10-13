"""Tiled detection helpers (research R3).

Small, far riders are found on 2x2 overlapping tiles; large, close riders on the full frame.
Tile boxes that touch an inner tile border are dropped (the person is cut off there and is
found whole on the full frame or another tile), then duplicates are merged with class-wise NMS.
"""

from __future__ import annotations

import math

import numpy as np
import torch
from numpy.typing import NDArray
from torchvision.ops import batched_nms  # pyright: ignore[reportMissingTypeStubs]

Window = tuple[int, int, int, int]  # x0, y0, x1, y1


def tile_windows(width: int, height: int, overlap_frac: float) -> list[Window]:
    tw = min(width, math.ceil(width * (0.5 + overlap_frac / 2)))
    th = min(height, math.ceil(height * (0.5 + overlap_frac / 2)))
    xs = sorted({0, width - tw})
    ys = sorted({0, height - th})
    return [(x, y, x + tw, y + th) for y in ys for x in xs]


def touches_inner_border(
    box: NDArray[np.float64], window: Window, width: int, height: int, margin: float = 2.0
) -> bool:
    x0, y0, x1, y1 = window
    bx0, by0, bx1, by1 = box
    return bool(
        (x0 > 0 and bx0 <= x0 + margin)
        or (y0 > 0 and by0 <= y0 + margin)
        or (x1 < width and bx1 >= x1 - margin)
        or (y1 < height and by1 >= y1 - margin)
    )


def merge(
    boxes: NDArray[np.float64],
    scores: NDArray[np.float64],
    classes: NDArray[np.int64],
    iou: float,
) -> NDArray[np.int64]:
    """Indices of the boxes kept after class-wise non-maximum suppression."""
    if len(boxes) == 0:
        return np.zeros(0, dtype=np.int64)
    keep = batched_nms(
        torch.as_tensor(boxes, dtype=torch.float32),
        torch.as_tensor(scores, dtype=torch.float32),
        torch.as_tensor(classes, dtype=torch.int64),
        iou,
    )
    return np.sort(keep.cpu().numpy().astype(np.int64))

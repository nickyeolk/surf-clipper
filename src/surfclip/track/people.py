"""Per-person cues derived from detection boxes: frame edge, stance, board under the feet.

All thresholds are relative (fractions of frame size, box aspect ratios, box heights), never
raw pixels (constitution III).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from surfclip.config import TrackConfig
from surfclip.rides.evidence import Edge, Stance
from surfclip.store.schemas import Point

Box = tuple[float, float, float, float]


def frame_edge(box: Box, width: int, height: int, cfg: TrackConfig) -> Edge:
    x0, y0, x1, y1 = box
    mx, my = cfg.edge_margin_frac * width, cfg.edge_margin_frac * height
    if x0 <= mx:
        return "left"
    if x1 >= width - mx:
        return "right"
    if y1 >= height - my:
        return "bottom"
    if y0 <= my:
        return "top"
    return "none"


def stance(box: Box, cfg: TrackConfig) -> Stance:
    w, h = box[2] - box[0], box[3] - box[1]
    if w <= 0 or h <= 0:
        return "unknown"
    aspect = h / w
    if aspect < cfg.sitting_max_aspect:
        return "sitting"
    if aspect < cfg.crouched_max_aspect:
        return "crouched"
    return "standing"


def _bottom_centre(box: Box) -> Point:
    return ((box[0] + box[2]) / 2, box[3])


def match_boards(
    people: Sequence[Box], boards: Sequence[Box], cfg: TrackConfig
) -> list[int | None]:
    """For each person, the index of the board under their feet (each board used once)."""
    pairs: list[tuple[float, int, int]] = []
    for pi, p in enumerate(people):
        fx, fy = _bottom_centre(p)
        reach = cfg.board_reach_heights * (p[3] - p[1])
        for bi, b in enumerate(boards):
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            d = float(np.hypot(cx - fx, cy - fy))
            if d <= reach:
                pairs.append((d, pi, bi))
    result: list[int | None] = [None] * len(people)
    used: set[int] = set()
    for _, pi, bi in sorted(pairs):
        if result[pi] is None and bi not in used:
            result[pi] = bi
            used.add(bi)
    return result


def feet_point(box: Box, board: Box | None, edge: Edge) -> Point:
    """Bottom centre of the box; when the bottom is cut off by the frame, the board centre."""
    if edge == "bottom" and board is not None:
        return ((board[0] + board[2]) / 2, (board[1] + board[3]) / 2)
    return _bottom_centre(box)

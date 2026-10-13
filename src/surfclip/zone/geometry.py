"""Pool coordinates (constitution III, FR-006, FR-007).

Positions used for decisions are in a top-down pool plane ``(u, v)`` in [0, 1]^2:

* ``u`` runs along the wave, from side wall ``a`` (u=0) to side wall ``b`` (u=1); riders enter
  over the side walls and ride along ``u``;
* ``v`` runs from the back wall (v=0) to the front of the zone (v=1).

Corners are identified by role, never by image left/right, so filming from the other side
of the wave gives the same pool coordinates for the same physical point.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from surfclip.store.schemas import Matrix3, Point, ZoneCorners

FloatArray = NDArray[np.float64]

_UNIT_SQUARE = np.array([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])


class GeometryError(ValueError):
    pass


def _cross(o: FloatArray, a: FloatArray, b: FloatArray) -> float:
    return float((a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]))


def _segments_cross(p1: FloatArray, p2: FloatArray, q1: FloatArray, q2: FloatArray) -> bool:
    d1, d2 = _cross(q1, q2, p1), _cross(q1, q2, p2)
    d3, d4 = _cross(p1, p2, q1), _cross(p1, p2, q2)
    return d1 * d2 < 0 and d3 * d4 < 0


def _check_quad(quad: FloatArray) -> None:
    """Quad in pool order (back_a, back_b, front_b, front_a) must be a simple polygon."""
    # Crossing first: a symmetric bowtie also has zero signed area.
    if _segments_cross(quad[0], quad[1], quad[2], quad[3]) or _segments_cross(
        quad[1], quad[2], quad[3], quad[0]
    ):
        raise GeometryError("zone edges cross: check which corner is which (back vs front)")
    x, y = quad[:, 0], quad[:, 1]
    area = 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))
    span = float(np.ptp(quad, axis=0).max())
    if span == 0 or area < 1e-3 * span * span:
        raise GeometryError("zone corners are collinear or too close together")


def _homography(src: FloatArray, dst: FloatArray) -> FloatArray:
    """Direct linear transform for exactly four point pairs."""
    rows: list[list[float]] = []
    rhs: list[float] = []
    for (x, y), (u, v) in zip(src, dst, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rhs.append(u)
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        rhs.append(v)
    h = np.linalg.solve(np.array(rows, dtype=np.float64), np.array(rhs, dtype=np.float64))
    return np.append(h, 1.0).reshape(3, 3)


def _apply(h: FloatArray, points: ArrayLike) -> FloatArray:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    homog = np.hstack([pts, np.ones((len(pts), 1))]) @ h.T
    return homog[:, :2] / homog[:, 2:3]


@dataclass(frozen=True)
class PoolMapping:
    image_to_pool: FloatArray
    pool_to_image: FloatArray

    @classmethod
    def from_corners(cls, corners: ZoneCorners) -> PoolMapping:
        quad = np.array(
            [corners.back_a, corners.back_b, corners.front_b, corners.front_a],
            dtype=np.float64,
        )
        _check_quad(quad)
        h = _homography(quad, _UNIT_SQUARE)
        return cls(h, np.linalg.inv(h))

    @classmethod
    def from_matrix(cls, matrix: Matrix3) -> PoolMapping:
        h = np.array(matrix, dtype=np.float64)
        return cls(h, np.linalg.inv(h))

    def as_tuple(self) -> Matrix3:
        r = [tuple(float(v) for v in row) for row in self.image_to_pool]
        return (
            (r[0][0], r[0][1], r[0][2]),
            (r[1][0], r[1][1], r[1][2]),
            (r[2][0], r[2][1], r[2][2]),
        )

    def to_pool(self, points: ArrayLike) -> FloatArray:
        return _apply(self.image_to_pool, points)

    def to_image(self, points: ArrayLike) -> FloatArray:
        return _apply(self.pool_to_image, points)


def point_in_polygon(point: Point, polygon: Sequence[Point]) -> bool:
    """Even-odd rule; points on an edge count as inside."""
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        (x1, y1), (x2, y2) = polygon[i], polygon[(i + 1) % n]
        # On-edge check (collinear and within the segment's bounding box).
        if (
            abs((x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)) < 1e-12
            and min(x1, x2) - 1e-12 <= x <= max(x1, x2) + 1e-12
            and min(y1, y2) - 1e-12 <= y <= max(y1, y2) + 1e-12
        ):
            return True
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def distance_in_heights(a: Point, b: Point, *, box_height_px: float) -> float:
    """Image distance expressed in units of a rider's current box height (local scale)."""
    if box_height_px <= 0:
        raise GeometryError("box height must be positive")
    return float(np.hypot(b[0] - a[0], b[1] - a[1])) / box_height_px

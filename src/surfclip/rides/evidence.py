"""Per-frame evidence for each tracked person (FR-006, FR-010, FR-013).

Every observation is placed in pool coordinates from its feet point. A person counts as a
riding *candidate* only when their feet are inside the wave zone, they are standing or crouched,
and a board is under their feet. When the box is cut off by the bottom of the frame (close
cameras, e.g. 20261012), the board is out of shot, so standing in the zone is enough. People on
an entry side wall (sitting, standing, holding a board) are never candidates, however much their
box overlaps the wave in the image.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np

from surfclip.config import RidesConfig
from surfclip.store.schemas import Point, SideWall, Zone
from surfclip.zone.geometry import PoolMapping

Stance = Literal["standing", "crouched", "sitting", "unknown"]
Edge = Literal["none", "left", "right", "top", "bottom"]
Region = Literal["zone", "side_wall", "outside"]


@dataclass(frozen=True, slots=True)
class Obs:
    """One tracked person in one analysed frame (image pixels)."""

    t: float
    frame: int
    track_id: int
    box: tuple[float, float, float, float]  # x1, y1, x2, y2
    feet: Point
    score: float
    board: bool
    stance: Stance
    edge: Edge  # frame edge the box touches, if any

    @property
    def box_height(self) -> float:
        return self.box[3] - self.box[1]


@dataclass(frozen=True, slots=True)
class Evidence:
    obs: Obs
    u: float
    v: float
    region: Region
    wall: SideWall | None
    candidate: bool

    @property
    def t(self) -> float:
        return self.obs.t


def _wall(u: float, cfg: RidesConfig) -> SideWall | None:
    if -cfg.wall_band_out_pool <= u <= cfg.wall_band_in_pool:
        return "side_a"
    if 1 - cfg.wall_band_in_pool <= u <= 1 + cfg.wall_band_out_pool:
        return "side_b"
    return None


def to_source_pixels(observations: Sequence[Obs], sx: float, sy: float) -> list[Obs]:
    """Scale analysis-frame observations to the source's displayed resolution.

    Zones are drawn on full-resolution keyframes (the picture the user sees), while detection
    runs on frames shrunk to the analysis height. Found on 2026-10-14: portrait and 1080p
    sessions produced no rides because the two were compared at different scales.
    """
    if sx == 1.0 and sy == 1.0:
        return list(observations)
    return [
        replace(
            o,
            box=(o.box[0] * sx, o.box[1] * sy, o.box[2] * sx, o.box[3] * sy),
            feet=(o.feet[0] * sx, o.feet[1] * sy),
        )
        for o in observations
    ]


def classify(
    observations: Sequence[Obs],
    zone: Zone,
    cfg: RidesConfig,
    face: tuple[float, float] | None = None,
) -> list[Evidence]:
    """Evidence for one track's observations, sorted by time.

    Observations and zone must be in the same pixel space: source display pixels.

    ``face`` is the wave face as a band of pool depth ``(v_min, v_max)``: riding also requires
    the feet on it (FR-015). Whitewater behind the wave is in the zone but off the face.
    """
    obs = sorted(observations, key=lambda o: o.t)
    if not obs:
        return []
    mapping = PoolMapping.from_corners(zone.corners)
    feet = np.array([o.feet for o in obs], dtype=np.float64)
    pool = mapping.to_pool(feet)
    on_plane = mapping.on_plane(feet)
    out: list[Evidence] = []
    for o, (u, v), plane in zip(obs, pool, on_plane, strict=True):
        u, v = float(u), float(v)
        in_depth = bool(plane) and -cfg.zone_margin_pool <= v <= 1 + cfg.zone_margin_pool
        wall = _wall(u, cfg) if in_depth else None
        region: Region
        if wall is not None and wall in zone.entry_walls:
            region = "side_wall"
        elif in_depth and cfg.wall_band_in_pool < u < 1 - cfg.wall_band_in_pool:
            region = "zone"
        else:
            region = "outside"
        on_board = o.board or o.edge == "bottom"  # board below the frame edge
        on_face = face is None or face[0] <= v <= face[1]
        candidate = (
            region == "zone" and on_face and on_board and o.stance in ("standing", "crouched")
        )
        out.append(Evidence(o, u, v, region, wall, candidate))
    return out

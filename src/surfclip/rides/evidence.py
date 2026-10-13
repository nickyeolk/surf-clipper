"""Per-frame evidence for each tracked person (FR-006, FR-010, FR-013).

Every observation is placed in pool coordinates from its feet point. A person counts as a
riding *candidate* only when their feet are inside the wave zone, they are standing or crouched,
and a board is under their feet. People on an entry side wall (sitting, standing, holding a
board) are never candidates, however much their box overlaps the wave in the image.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
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


def classify(observations: Sequence[Obs], zone: Zone, cfg: RidesConfig) -> list[Evidence]:
    """Evidence for one track's observations, sorted by time."""
    obs = sorted(observations, key=lambda o: o.t)
    if not obs:
        return []
    mapping = PoolMapping.from_corners(zone.corners)
    pool = mapping.to_pool(np.array([o.feet for o in obs], dtype=np.float64))
    out: list[Evidence] = []
    for o, (u, v) in zip(obs, pool, strict=True):
        u, v = float(u), float(v)
        in_depth = -cfg.zone_margin_pool <= v <= 1 + cfg.zone_margin_pool
        wall = _wall(u, cfg) if in_depth else None
        region: Region
        if wall is not None and wall in zone.entry_walls:
            region = "side_wall"
        elif in_depth and cfg.wall_band_in_pool < u < 1 - cfg.wall_band_in_pool:
            region = "zone"
        else:
            region = "outside"
        candidate = region == "zone" and o.board and o.stance in ("standing", "crouched")
        out.append(Evidence(o, u, v, region, wall, candidate))
    return out

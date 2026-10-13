"""Synthetic tracks for ride-logic tests (no video).

The zone is the unit square scaled to 1000 px: image point (u*1000, v*1000) is pool (u, v).
Side wall a is at u=0, side wall b at u=1. People are 100 px tall; analysis runs at 5 fps.
"""

from __future__ import annotations

from dataclasses import dataclass

from surfclip.config import RidesConfig, load_config
from surfclip.rides.evidence import Edge, Obs, Stance
from surfclip.store.schemas import Zone, ZoneCorners

FPS = 5.0
SOURCE_FPS = 30.0
BOX_H = 100.0

ZONE = Zone(
    epoch_id=0,
    corners=ZoneCorners(back_a=(0, 0), back_b=(1000, 0), front_a=(0, 1000), front_b=(1000, 1000)),
    origin="user",
)


def rides_cfg(**overrides: float) -> RidesConfig:
    return load_config(overrides={f"rides.{k}": v for k, v in overrides.items()}).rides


@dataclass(frozen=True)
class Seg:
    """A stretch of one track: moves linearly from (u0, v) to (u1, v) over `dur` seconds."""

    dur: float
    u0: float
    u1: float
    v: float = 0.4
    board: bool = True
    stance: Stance = "standing"
    edge: Edge = "none"
    score: float = 0.9


def track(track_id: int, start_t: float, *segs: Seg) -> list[Obs]:
    out: list[Obs] = []
    t = start_t
    for seg in segs:
        n = max(1, round(seg.dur * FPS))
        for i in range(n):
            u = seg.u0 + (seg.u1 - seg.u0) * (i / max(1, n - 1))
            x, y = u * 1000, seg.v * 1000
            out.append(
                Obs(
                    t=round(t, 6),
                    frame=round(t * SOURCE_FPS),
                    track_id=track_id,
                    box=(x - 25, y - BOX_H, x + 25, y),
                    feet=(x, y),
                    score=seg.score,
                    board=seg.board,
                    stance=seg.stance,
                    edge=seg.edge,
                )
            )
            t += 1 / FPS
    return out


def ride_segment(dur: float, u0: float = 0.1, u1: float = 0.8, **kw: object) -> Seg:
    return Seg(dur, u0, u1, **kw)  # type: ignore[arg-type]


def sitting_on_wall(dur: float, u: float = -0.05) -> Seg:
    return Seg(dur, u, u, v=0.3, board=False, stance="sitting")

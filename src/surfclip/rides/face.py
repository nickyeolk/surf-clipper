"""The wave face as a band of pool depth, estimated per session (FR-015).

Riding happens on the face; the whitewater behind it is in the zone but not part of a ride.
A first pass finds confirmed riding without the band; the band is where those riders' feet
cluster (low and high depth percentiles plus a margin). Percentiles, not min/max, so a few
frames in the whitewater (e.g. a cluster near the back wall in 20261012) do not widen it.
A zone with ``face_v`` set by the user overrides the estimate.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from pydantic import BaseModel

from surfclip.config import RidesConfig


class FaceBand(BaseModel):
    face_v: tuple[float, float] | None
    origin: str  # "zone" (user), "auto", or "none" (too little riding to estimate)
    frames: int


def estimate_face(on_wave_v: Sequence[float], cfg: RidesConfig) -> FaceBand:
    if cfg.face_band == "off":
        return FaceBand(face_v=None, origin="none", frames=len(on_wave_v))
    if len(on_wave_v) < cfg.face_min_frames:
        return FaceBand(face_v=None, origin="none", frames=len(on_wave_v))
    lo, hi = np.percentile(np.asarray(on_wave_v), [cfg.face_low_pct, cfg.face_high_pct])
    band = (round(float(lo) - cfg.face_margin_pool, 3), round(float(hi) + cfg.face_margin_pool, 3))
    return FaceBand(face_v=band, origin="auto", frames=len(on_wave_v))

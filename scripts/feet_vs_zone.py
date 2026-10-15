"""How moving riders' feet spread inside each session's hand-drawn zone (zone proposal design).

Usage: feet_vs_zone.py VIDEO [VIDEO ...] [--artifacts artifacts]
Prints percentiles of pool u and v for feet of people on boards that move across the frame.
"""

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np

from surfclip.edits.log import confirmed_zone, read_edits
from surfclip.rides.evidence import Obs, to_source_pixels
from surfclip.stages import source_scale
from surfclip.store.frames import read_meta, read_observations
from surfclip.store.schemas import SourceInfo
from surfclip.store.session import SessionStore
from surfclip.zone.geometry import PoolMapping

ap = argparse.ArgumentParser()
ap.add_argument("videos", type=Path, nargs="+")
ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
args = ap.parse_args()
Q = [0.5, 1, 2, 5, 50, 95, 98, 99, 99.5]
for video in args.videos:
    store = SessionStore.open(video, args.artifacts)
    zone = confirmed_zone(read_edits(store))
    assert zone is not None
    tf = store.path("tracks.parquet")
    sx, sy = source_scale(store.read_model("probe.json", SourceInfo), read_meta(tf))
    by: dict[int, list[Obs]] = defaultdict(list)
    for o in to_source_pixels(read_observations(tf), sx, sy):
        by[o.track_id].append(o)
    pts: list[tuple[float, float]] = []
    for obs in by.values():
        for a, b in zip(obs, obs[1:], strict=False):
            dt = b.t - a.t
            if dt <= 0 or not (b.board and b.stance in ("standing", "crouched")):
                continue
            speed = np.hypot(b.feet[0] - a.feet[0], b.feet[1] - a.feet[1]) / dt / b.box_height
            if speed >= 0.3:  # rider heights per second
                pts.append(b.feet)
    uv = PoolMapping.from_corners(zone.corners).to_pool(pts)
    print(f"{video.stem}: {len(pts)} moving board feet")
    print("  u " + " ".join(f"{q}%:{np.percentile(uv[:, 0], q):.2f}" for q in Q))
    print("  v " + " ".join(f"{q}%:{np.percentile(uv[:, 1], q):.2f}" for q in Q))

"""Distances between rides' appearance in a session, and group counts per cut-off.

Usage: rider_distances.py VIDEO [--artifacts artifacts]
Reads appearance.parquet and rides.json; prints percentiles of the pairwise distances of rides
far apart in time, and how many groups each cut-off gives.
"""

import argparse
from pathlib import Path

import numpy as np

from surfclip.config import load_config
from surfclip.riders.cluster import group_rides
from surfclip.riders.session import _load, ride_key  # pyright: ignore[reportPrivateUsage]
from surfclip.store.schemas import Rides
from surfclip.store.session import SessionStore

ap = argparse.ArgumentParser()
ap.add_argument("video", type=Path)
ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
args = ap.parse_args()
store = SessionStore.open(args.video, args.artifacts)
cfg = load_config(overrides=store.session.config_overrides)
app = _load(store)
assert app is not None
rides = store.read_model("rides.json", Rides).rides
vec = {
    r.ride_id: app.rides[ride_key(r)].desc.vector
    for r in rides
    if ride_key(r) in app.rides and app.rides[ride_key(r)].desc.crops > 0
}
spans = {r.ride_id: (r.start_s, r.end_s) for r in rides}
ids = list(vec)
d = [app.distance(vec[a], vec[b]) for i, a in enumerate(ids) for b in ids[i + 1 :]]
print(f"{len(ids)} rides, hue weight {app.hue_weight}")
print(
    "pairwise distance percentiles:",
    {q: round(float(np.percentile(d, q)), 3) for q in (1, 5, 10, 25, 50, 75)},
)
for t in (0.05, 0.08, 0.1, 0.12, 0.15, 0.2, 0.25, 0.3):
    groups = group_rides(
        vec, spans, app.distance, threshold=t, overlap_allowed_s=cfg.rides.changeover_overlap_max_s
    )
    print(f"cut {t:.2f}: {len(groups)} groups, sizes {[len(g) for g in groups][:12]}")

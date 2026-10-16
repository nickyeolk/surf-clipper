"""Spike (004): how tall are riders, in source pixels, during rides in each session?

Usage: rider_sizes.py [--artifacts artifacts]
"""

import argparse
from pathlib import Path

import numpy as np

from surfclip.stages import session_observations
from surfclip.store.schemas import Rides, Session, SourceInfo
from surfclip.store.session import SessionStore

ap = argparse.ArgumentParser()
ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
args = ap.parse_args()

for folder in sorted(args.artifacts.iterdir()):
    if not (folder / "rides.json").exists():
        continue
    session = Session.model_validate_json((folder / "session.json").read_text(encoding="utf-8"))
    store = SessionStore(folder, session)
    info = store.read_model("probe.json", SourceInfo)
    rides = store.read_model("rides.json", Rides).rides
    tracks = {t: r for r in rides for t in r.track_ids}
    h = [
        o.box_height
        for o in session_observations(store)
        if o.track_id in tracks and tracks[o.track_id].start_s <= o.t <= tracks[o.track_id].end_s
    ]
    if not h:
        continue
    p10, p50, p90 = np.percentile(h, [10, 50, 90])
    print(
        f"{Path(info.path).name:34s} {info.width}x{info.height} {info.hdr_format:5s} "
        f"rider height px: p10 {p10:4.0f}  median {p50:4.0f}  p90 {p90:4.0f}"
    )

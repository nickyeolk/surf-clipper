"""How the box-shape stance rule labels people while they ride, per session.

Usage: stance_report.py VIDEO [VIDEO ...] [--artifacts artifacts]
Box aspect = height / width. Stance: < sitting_max_aspect sitting, < crouched_max_aspect crouched,
else standing. "Riding" = frames inside a detected ride's track(s) and time span.
"""

import argparse
from collections import Counter
from pathlib import Path

import numpy as np

from surfclip.config import load_config
from surfclip.stages import session_observations
from surfclip.store.schemas import Rides
from surfclip.store.session import SessionStore

ap = argparse.ArgumentParser()
ap.add_argument("videos", type=Path, nargs="+")
ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
args = ap.parse_args()
for video in args.videos:
    store = SessionStore.open(video, args.artifacts)
    cfg = load_config(overrides=store.session.config_overrides).track
    rides = store.read_model("rides.detected.json", Rides).rides
    spans: dict[int, list[tuple[float, float]]] = {}
    for r in rides:
        for t in r.track_ids:
            spans.setdefault(t, []).append((r.start_s, r.end_s))
    riding = [
        o
        for o in session_observations(store)
        if any(s <= o.t <= e for s, e in spans.get(o.track_id, []))
    ]
    counts = Counter(o.stance for o in riding)
    aspect = np.array([o.box_height / max(o.box[2] - o.box[0], 1.0) for o in riding])
    n = len(riding)
    print(f"{video.stem}: {n} riding observations")
    print("  stance  " + "  ".join(f"{k} {v / n:.0%}" for k, v in counts.most_common()))
    print(
        "  aspect  "
        + "  ".join(f"p{q} {np.percentile(aspect, q):.2f}" for q in (5, 25, 50, 75, 95))
        + f"   (thresholds: sitting < {cfg.sitting_max_aspect}, crouched < {cfg.crouched_max_aspect})"
    )

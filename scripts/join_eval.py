"""Ride metrics (001) before and after joining rides split at the frame edge (002 FR-011).

Usage: join_eval.py VIDEO [VIDEO ...] [--artifacts artifacts] [--labels-dir labels/rides]
In memory only: groups the detected rides, finds joins, scores both against the ride labels.
"""

import argparse
from pathlib import Path

from surfclip.config import load_config
from surfclip.edits.apply import apply_joins
from surfclip.eval.labels import SessionLabels
from surfclip.eval.metrics import Span, evaluate
from surfclip.eval.riders import detected_grouping
from surfclip.riders.joins import find_joins
from surfclip.store.schemas import Rides
from surfclip.store.session import SessionStore

ap = argparse.ArgumentParser()
ap.add_argument("videos", type=Path, nargs="+")
ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
ap.add_argument("--labels-dir", type=Path, default=Path("labels/rides"))
args = ap.parse_args()


def score(rides: Rides, labels: SessionLabels) -> str:
    m = evaluate([Span(r.start_s, r.end_s) for r in rides.rides], labels.rides,
                 min_length_s=rides.settings.min_length_s, pad_before_s=rides.settings.pad_before_s,
                 pad_after_s=rides.settings.pad_after_s)  # fmt: skip
    return f"recall {m.recall:6.1%}  precision {m.precision:6.1%}  complete {m.completeness:6.1%}"


for video in args.videos:
    store = SessionStore.open(video, args.artifacts)
    cfg = load_config(overrides=store.session.config_overrides)
    labels = SessionLabels.model_validate_json(
        (args.labels_dir / f"{video.stem}.json").read_text(encoding="utf-8")
    )
    detected, riders = detected_grouping(store, cfg)
    auto, suggestions = find_joins(detected.rides, riders, cfg.riders)
    joined = apply_joins(detected, auto, [])
    print(f"== {video.stem}: {len(auto)} automatic joins, {len(suggestions)} suggestions")
    print(f"   before  {score(detected, labels)}")
    print(f"   after   {score(joined, labels)}")

"""Completeness and tightness for a grid of clip paddings, per labelled session.

Usage: pad_sweep.py VIDEO [VIDEO ...] [--artifacts artifacts] [--labels-dir labels/rides]
"""

import argparse
from pathlib import Path

from surfclip.eval.labels import SessionLabels
from surfclip.eval.metrics import Span, evaluate
from surfclip.store.schemas import Rides
from surfclip.store.session import SessionStore

ap = argparse.ArgumentParser()
ap.add_argument("videos", type=Path, nargs="+")
ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
ap.add_argument("--labels-dir", type=Path, default=Path("labels/rides"))
args = ap.parse_args()
grid = [(b, a) for b in (1.0, 1.5, 2.0) for a in (1.5, 2.0, 2.5, 3.0)]
print("session".ljust(22) + "".join(f"  {b:.1f}/{a:.1f}  " for b, a in grid))
for video in args.videos:
    store = SessionStore.open(video, args.artifacts)
    labels = SessionLabels.model_validate_json(
        (args.labels_dir / f"{video.stem}.json").read_text(encoding="utf-8")
    )
    rides = store.read_model("rides.json", Rides)
    cells: list[str] = []
    for b, a in grid:
        m = evaluate(
            [Span(r.start_s, r.end_s) for r in rides.rides],
            labels.rides,
            min_length_s=rides.settings.min_length_s,
            pad_before_s=b,
            pad_after_s=a,
        )
        cells.append(f"{m.completeness:5.1%} {m.overhang_p95:3.1f}s")
    print(video.stem.ljust(22) + "  ".join(cells))

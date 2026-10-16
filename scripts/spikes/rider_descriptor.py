"""T014 spike: colour vs DINOv2 embedding vs both, scored on the rider labels (SC-001).

Usage: rider_descriptor.py VIDEO [VIDEO ...] --held-out NAME [--artifacts artifacts]
Describes the detected rides with both descriptors (cached in appearance.parquet), then sweeps
the grouping cut-off per descriptor. The cut-off is chosen on the tuning sessions only; the
held-out session is scored once at the chosen setting.
"""

import argparse
import time
from pathlib import Path

import numpy as np

from surfclip.config import load_config
from surfclip.eval.riders import RiderLabels, evaluate_riders
from surfclip.eval.metrics import Span, iou
from surfclip.riders.session import build_riders, describe_rides, ride_key
from surfclip.stages import session_observations
from surfclip.store.schemas import Rides
from surfclip.store.session import SessionStore

GRIDS = {
    "colour": [round(x, 3) for x in np.arange(0.06, 0.32, 0.02)],
    "embedding": [round(x, 3) for x in np.arange(0.04, 0.13, 0.005)],
    "both": [round(x, 3) for x in np.arange(0.3, 1.3, 0.05)],
}

ap = argparse.ArgumentParser()
ap.add_argument("videos", type=Path, nargs="+")
ap.add_argument("--held-out", required=True)
ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
args = ap.parse_args()

sessions = []
for video in args.videos:
    store = SessionStore.open(video, args.artifacts)
    cfg = load_config(overrides={**store.session.config_overrides, "riders.descriptor": "both"})
    detected = store.read_model("rides.detected.json", Rides)
    t0 = time.perf_counter()
    app = describe_rides(store, detected.rides, session_observations(store), cfg.riders)
    secs = time.perf_counter() - t0
    labels = RiderLabels.model_validate_json(
        (Path("labels/riders") / f"{video.stem}.json").read_text(encoding="utf-8")
    )
    # Distances between rides of the same and of different labelled riders, per descriptor.
    truth: dict[str, str] = {}
    for lab in labels.rides:
        best = max(
            detected.rides,
            key=lambda d: iou(Span(lab.start_s, lab.end_s), Span(d.start_s, d.end_s)),
        )
        if iou(Span(lab.start_s, lab.end_s), Span(best.start_s, best.end_s)) >= 0.5:
            truth[best.ride_id] = lab.rider
    print(f"== {video.stem}: described in {secs:.0f}s; {len(truth)} labelled rides matched")
    for mode in GRIDS:
        a = app.with_mode(mode)  # type: ignore[arg-type]
        vec = {
            r.ride_id: a.vector(a.rides[ride_key(r)])
            for r in detected.rides
            if ride_key(r) in a.rides and a.usable(a.rides[ride_key(r)]) and r.ride_id in truth
        }
        ids = list(vec)
        same = [
            a.distance(vec[x], vec[y])
            for i, x in enumerate(ids)
            for y in ids[i + 1 :]
            if truth[x] == truth[y]
        ]
        diff = [
            a.distance(vec[x], vec[y])
            for i, x in enumerate(ids)
            for y in ids[i + 1 :]
            if truth[x] != truth[y]
        ]
        print(
            f"   {mode:9s} same-rider median {np.median(same):.3f}  different-rider median {np.median(diff):.3f}"
            f"  (separation {np.median(diff) / max(np.median(same), 1e-9):.2f}x)"
        )
    sessions.append((video.stem, store, app, detected, labels, cfg))

results: dict[str, dict[float, dict[str, float]]] = {m: {} for m in GRIDS}
for mode, grid in GRIDS.items():
    for t in grid:
        for name, _store, app, detected, labels, cfg in sessions:
            c = cfg.riders.model_copy(update={"cluster_threshold": t, "descriptor": mode})
            riders = build_riders(
                "s",
                detected.rides,
                app.with_mode(mode),
                c,  # type: ignore[arg-type]
                overlap_allowed_s=cfg.rides.changeover_overlap_max_s,
            )
            results[mode].setdefault(t, {})[name] = evaluate_riders(
                labels, detected, riders
            ).accuracy

print(
    "\nSC-001 (share of rides in their rider's group) at the best cut-off on the tuning sessions:"
)
for mode, by_t in results.items():
    tuning = {t: [v for n, v in accs.items() if n != args.held_out] for t, accs in by_t.items()}
    best_t = max(tuning, key=lambda t: (min(tuning[t]), np.mean(tuning[t])))
    accs = by_t[best_t]
    cells = "  ".join(f"{n[:14]} {v:5.1%}" for n, v in accs.items())
    print(
        f"  {mode:9s} cut {best_t:5.3f}: {cells}  | tuning min {min(tuning[best_t]):.1%} mean {np.mean(tuning[best_t]):.1%}"
    )

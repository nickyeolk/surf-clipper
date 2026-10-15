"""Score zone proposals: agreement with the hand-drawn zone, and rides found with the proposal.

Usage: zone_proposal_eval.py VIDEO [VIDEO ...] [--artifacts artifacts] [--labels-dir labels/rides]
Writes each proposal to artifacts/review/zone_proposal_<name>.json (for draw_zone.py).
Nothing in the session is changed: rides are computed in memory.
"""

import argparse
from pathlib import Path

import numpy as np

from surfclip.config import load_config
from surfclip.edits.log import confirmed_zone, read_edits
from surfclip.eval.labels import SessionLabels
from surfclip.eval.metrics import Span, evaluate
from surfclip.stages import detect_rides, session_observations
from surfclip.store.schemas import Rides, SourceInfo
from surfclip.store.session import SessionStore
from surfclip.zone.editing import display_size
from surfclip.zone.geometry import PoolMapping
from surfclip.zone.propose import propose_zone, riding_feet

ap = argparse.ArgumentParser()
ap.add_argument("videos", type=Path, nargs="+")
ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
ap.add_argument("--labels-dir", type=Path, default=Path("labels/rides"))
args = ap.parse_args()
out_dir = args.artifacts / "review"
out_dir.mkdir(parents=True, exist_ok=True)


def score(rides: Rides, labels: SessionLabels) -> str:
    m = evaluate(
        [Span(r.start_s, r.end_s) for r in rides.rides],
        labels.rides,
        min_length_s=rides.settings.min_length_s,
        pad_before_s=rides.settings.pad_before_s,
        pad_after_s=rides.settings.pad_after_s,
    )
    return (
        f"recall {m.recall:6.1%}  precision {m.precision:6.1%}  complete {m.completeness:6.1%}"
        f"  tight {m.overhang_p95:4.2f}s"
    )


for video in args.videos:
    store = SessionStore.open(video, args.artifacts)
    cfg = load_config(overrides=store.session.config_overrides)
    hand = confirmed_zone(read_edits(store))
    assert hand is not None
    w, h = display_size(store.read_model("probe.json", SourceInfo))
    obs = session_observations(store)
    prop = propose_zone(obs, w, h)
    (out_dir / f"zone_proposal_{video.stem}.json").write_text(prop.zone.model_dump_json(indent=2))
    feet = riding_feet(obs).feet
    # Mirror-invariant comparison: a and b may be swapped.
    uv_hand = PoolMapping.from_corners(hand.corners).to_pool(feet)
    uv_prop = PoolMapping.from_corners(prop.zone.corners).to_pool(feet)
    ok = np.all(np.isfinite(uv_hand), axis=1) & (np.abs(uv_hand).max(axis=1) < 3)
    du = min(
        float(np.median(np.abs(uv_prop[ok, 0] - uv_hand[ok, 0]))),
        float(np.median(np.abs(1 - uv_prop[ok, 0] - uv_hand[ok, 0]))),
    )
    dv = float(np.median(np.abs(uv_prop[ok, 1] - uv_hand[ok, 1])))
    print(
        f"== {video.stem}: confidence {prop.confidence} unreliable={prop.unreliable} "
        f"points={prop.points} walls in frame={prop.walls_in_frame}"
    )
    for note in prop.notes:
        print(f"   note: {note}")
    print(f"   median |du| {du:.3f}  |dv| {dv:.3f} (riding feet, proposal vs hand zone)")
    label_file = args.labels_dir / f"{video.stem}.json"
    if label_file.exists():
        labels = SessionLabels.model_validate_json(label_file.read_text(encoding="utf-8"))
        rides_prop, _, _ = detect_rides(store, prop.zone, cfg.rides)
        print(f"   hand zone:  {score(store.read_model('rides.detected.json', Rides), labels)}")
        print(f"   proposal:   {score(rides_prop, labels)}")

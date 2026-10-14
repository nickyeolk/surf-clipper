"""List matched rides with boundary errors above a threshold, plus misses and false rides.

Usage: eval_details.py VIDEO [--min-err 1.0] [--artifacts artifacts] [--labels-dir labels/rides]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from surfclip.eval.labels import SessionLabels, fmt_time
from surfclip.eval.metrics import IOU_MATCH, Span, iou
from surfclip.store.schemas import Rides
from surfclip.store.session import SessionStore


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--min-err", type=float, default=1.0)
    ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    ap.add_argument("--labels-dir", type=Path, default=Path("labels/rides"))
    args = ap.parse_args()
    store = SessionStore.open(args.video, args.artifacts)
    rides = store.read_model("rides.json", Rides).rides
    labels = SessionLabels.model_validate_json(
        (args.labels_dir / f"{args.video.stem}.json").read_text(encoding="utf-8")
    ).rides
    used: set[int] = set()
    for lab in labels:
        ls = Span(lab.start_s, lab.end_s)
        best = max(
            ((iou(Span(r.start_s, r.end_s), ls), i) for i, r in enumerate(rides) if i not in used),
            default=(0.0, -1),
        )
        if best[0] < IOU_MATCH:
            print(
                f"MISSED  label {fmt_time(lab.start_s)}-{fmt_time(lab.end_s)} "
                f"({lab.end_s - lab.start_s:.1f}s)"
            )
            continue
        used.add(best[1])
        r = rides[best[1]]
        ds, de = r.start_s - lab.start_s, r.end_s - lab.end_s
        cut = ds > 1.0 + 1e-6 or de < -1.5 - 1e-6  # clip padding is 1 s before, 1.5 s after
        if cut or max(abs(ds), abs(de)) >= args.min_err:
            print("CUT  " if cut else "     ", end="")
            print(
                f"{r.ride_id}  label {fmt_time(lab.start_s)}-{fmt_time(lab.end_s)}  "
                f"start {ds:+6.2f}s  end {de:+6.2f}s  ({r.start_kind}, label origin {lab.origin})"
            )
    for i, r in enumerate(rides):
        if i not in used:
            print(
                f"FALSE   {r.ride_id} {fmt_time(r.start_s)}-{fmt_time(r.end_s)} "
                f"({r.end_s - r.start_s:.1f}s, {r.start_kind})"
            )


if __name__ == "__main__":
    main()

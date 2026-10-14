"""Mark rejected rides in a lesson stretch as correct (user decision 2026-10-15: lessons are rides,
flagged "lesson"). Lists what it would change; --apply writes the work file and re-finalizes.

Usage: relabel_lessons.py WORK.json VIDEO --until SECONDS [--apply] [--artifacts artifacts]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from surfclip.eval.labels import LabelWork, finalize, fmt_time
from surfclip.store.schemas import Rides
from surfclip.store.session import SessionStore


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("work", type=Path)
    ap.add_argument("video", type=Path)
    ap.add_argument("--until", type=float, required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    args = ap.parse_args()
    work = LabelWork.model_validate_json(args.work.read_text(encoding="utf-8"))
    rides = SessionStore.open(args.video, args.artifacts).read_model("rides.json", Rides)
    lesson_ids = {r.ride_id for r in rides.rides if r.flags.lesson and r.start_s < args.until}
    changed = 0
    for item in work.items:
        lesson = item.id in lesson_ids or (
            item.detected_as != "short" and item.start_s < args.until
        )
        if item.verdict == "no" and lesson:
            print(
                f"{item.id:12s} {fmt_time(item.start_s)}-{fmt_time(item.end_s)} "
                f"{item.detected_as} -> ok"
            )
            item.verdict = "ok"
            changed += 1
    print(f"{changed} items to change")
    if args.apply and changed:
        args.work.write_text(work.model_dump_json(indent=2), encoding="utf-8")
        out = args.work.with_name(args.work.name.replace(".work.json", ".json"))
        out.write_text(finalize(work).model_dump_json(indent=2), encoding="utf-8")
        print(f"wrote {args.work} and {out}")


if __name__ == "__main__":
    main()

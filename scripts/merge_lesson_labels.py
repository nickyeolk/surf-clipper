"""Merge the kept label items of a lesson stretch into one ride (user decision 2026-10-15: a
lesson is one ride). The longest item absorbs the others' span; the rest become "no".

Usage: merge_lesson_labels.py WORK.json --until SECONDS [--apply]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from surfclip.eval.labels import LabelWork, finalize, fmt_time


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("work", type=Path)
    ap.add_argument("--until", type=float, required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    work = LabelWork.model_validate_json(args.work.read_text(encoding="utf-8"))
    lesson = [i for i in work.items if i.verdict != "no" and i.start_s < args.until]
    if len(lesson) < 2:
        print("nothing to merge")
        return
    keep = max(lesson, key=lambda i: i.end_s - i.start_s)
    start, end = min(i.start_s for i in lesson), max(i.end_s for i in lesson)
    for i in lesson:
        if i is not keep:
            i.verdict = "no"
            i.notes = f"merged into lesson ride {keep.id}"
    keep.start_s, keep.end_s, keep.verdict = start, end, "fix"
    keep.notes = "whole lesson as one ride"
    print(f"lesson ride {keep.id}: {fmt_time(start)}-{fmt_time(end)} from {len(lesson)} items")
    if args.apply:
        args.work.write_text(work.model_dump_json(indent=2), encoding="utf-8")
        out = args.work.with_name(args.work.name.replace(".work.json", ".json"))
        out.write_text(finalize(work).model_dump_json(indent=2), encoding="utf-8")
        print(f"wrote {args.work} and {out}")


if __name__ == "__main__":
    main()

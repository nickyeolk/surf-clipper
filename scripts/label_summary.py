"""Summarise a label work file: verdict counts and rides contained in other rides.

Usage: label_summary.py labels/rides/<name>.work.json
"""

import sys
from collections import Counter
from pathlib import Path

from surfclip.eval.labels import LabelWork

work = LabelWork.model_validate_json(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("verdicts:", dict(Counter(i.verdict for i in work.items)))
print(
    "detected_as of kept rides:",
    dict(Counter(i.detected_as for i in work.items if i.verdict != "no")),
)
print(f"scanned to {work.scanned_to_s:.0f} s, finalized {work.finalized}")
kept = sorted((i for i in work.items if i.verdict != "no"), key=lambda i: i.start_s)
eps = 0.05
for outer in kept:
    for inner in kept:
        if inner is outer:
            continue
        if outer.start_s - eps <= inner.start_s and inner.end_s <= outer.end_s + eps:
            print(
                f"contained: {inner.id} {inner.start_s:.1f}-{inner.end_s:.1f} ({inner.verdict}) "
                f"inside {outer.id} {outer.start_s:.1f}-{outer.end_s:.1f} ({outer.verdict})"
            )
overlaps = [
    (a, b)
    for a, b in zip(kept, kept[1:], strict=False)
    if b.start_s < a.end_s - eps and not (b.end_s <= a.end_s + eps)
]
for a, b in overlaps:
    print(f"overlap: {a.id} ends {a.end_s:.1f}, {b.id} starts {b.start_s:.1f}")

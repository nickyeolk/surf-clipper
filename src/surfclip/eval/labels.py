"""Hand labels, proposed by the tool and validated by the user (research R15).

Two ways to validate:

* **Review UI, label mode** (preferred): a working document ``labels/rides/<name>.work.json``
  holds one item per proposed ride with the user's verdict, saved as they go. Finalising writes
  ``labels/rides/<name>.json``. Label work never changes the detected rides or edits.json.
* **CSV** (fallback):

1. ``surfclip labels propose VIDEO`` writes ``labels/rides/<name>.csv`` from the detected rides
   and short attempts, every row with verdict ``?``.
2. The user plays the video (e.g. in VLC), sets each row's verdict to ``ok``, ``fix`` (with
   ``new_start``/``new_end``) or ``no``, adds rows with verdict ``add`` for missed rides, and
   ticks ``acid_drop`` where the ride starts with a jump from a side wall. For the held-out
   session the whole video must be scanned for misses.
3. ``surfclip labels import CSV`` writes ``labels/rides/<name>.json``; evaluation uses only
   validated rows and refuses files that still contain ``?``.

Times are written as ``mm:ss.ss`` (or ``h:mm:ss.ss``) so they can be typed from a player.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from surfclip.eval.metrics import LabelRide
from surfclip.store.schemas import SCHEMA_VERSION, Rides

CSV_COLUMNS = [
    "id",
    "start",
    "end",
    "length_s",
    "detected_as",
    "confidence",
    "verdict",
    "new_start",
    "new_end",
    "acid_drop",
    "notes",
]
Verdict = Literal["?", "ok", "fix", "no", "add"]


class LabelError(ValueError):
    pass


class SessionLabels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    source: str
    rides: list[LabelRide] = Field(default_factory=list[LabelRide])
    camera_shifts_s: list[float] = Field(default_factory=list[float])


class LabelItem(BaseModel):
    """One ride in the label working document."""

    model_config = ConfigDict(extra="forbid")

    id: str
    start_s: float
    end_s: float
    verdict: Verdict = "?"
    acid_drop: bool = False
    detected_as: str | None = None  # start kind or "short"; None for rides the user added
    proposed_start_s: float | None = None
    proposed_end_s: float | None = None
    confidence: float | None = None
    notes: str = ""


class LabelWork(BaseModel):
    """Label progress for one session, saved as the user goes (labels/rides/<name>.work.json)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    source: str
    items: list[LabelItem] = Field(default_factory=list[LabelItem])
    scanned_to_s: float = 0.0  # how far the user has scanned the whole video for missed rides
    finalized: bool = False

    @property
    def remaining(self) -> int:
        return sum(1 for i in self.items if i.verdict == "?")


Origin = Literal["accepted", "corrected", "added"]
_ORIGIN: dict[str, Origin] = {"ok": "accepted", "fix": "corrected", "add": "added"}


def work_from_rides(rides: Rides, source: str) -> LabelWork:
    items = [
        LabelItem(
            id=r.ride_id,
            start_s=r.start_s,
            end_s=r.end_s,
            detected_as=r.start_kind,
            acid_drop=r.start_kind == "acid_drop",
            proposed_start_s=r.start_s,
            proposed_end_s=r.end_s,
            confidence=r.confidence,
        )
        for r in rides.rides
    ] + [
        LabelItem(
            id=s.ride_id,
            start_s=s.start_s,
            end_s=s.end_s,
            detected_as="short",
            proposed_start_s=s.start_s,
            proposed_end_s=s.end_s,
            confidence=s.confidence,
        )
        for s in rides.short_attempts
    ]
    return LabelWork(source=source, items=sorted(items, key=lambda i: i.start_s))


CONTAIN_TOL_S = 0.5
MIN_LABEL_S = 0.5


def _origin(item: LabelItem) -> Origin:
    if item.verdict == "add" or item.detected_as is None:
        return "added"
    moved = (
        item.proposed_start_s is not None
        and item.proposed_end_s is not None
        and (
            abs(item.start_s - item.proposed_start_s) > 1e-3
            or abs(item.end_s - item.proposed_end_s) > 1e-3
        )
    )
    return "corrected" if moved or item.verdict == "fix" else "accepted"


def contained_ids(items: Sequence[LabelItem]) -> set[str]:
    """Kept items lying entirely within another kept item (within CONTAIN_TOL_S).

    A rider who touches a side wall mid-ride can be split into two proposed rides; extending
    the first one to the true end covers the second, which is then part of it, not a ride of
    its own (seen on 20240924). Only an outer ride the user extended or added absorbs others:
    simultaneous riders (a group lesson, 20241004) overlap without anyone editing anything.
    """
    kept = [i for i in items if i.verdict != "no"]
    inside: set[str] = set()
    for inner in kept:
        for outer in kept:
            if outer is inner or outer.id in inside:
                continue
            longer = (outer.end_s - outer.start_s) > (inner.end_s - inner.start_s)
            if (
                longer
                and _origin(outer) in ("corrected", "added")
                and outer.start_s - CONTAIN_TOL_S <= inner.start_s
                and inner.end_s <= outer.end_s + CONTAIN_TOL_S
            ):
                inside.add(inner.id)
                break
    return inside


def finalize(work: LabelWork) -> SessionLabels:
    if work.remaining:
        raise LabelError(f"{work.remaining} rides still need a verdict")
    inside = contained_ids(work.items)
    rides: list[LabelRide] = []
    for item in work.items:
        if item.verdict == "no" or item.id in inside:
            continue
        if item.end_s - item.start_s < MIN_LABEL_S:
            continue  # an accidental zero-length edit
        rides.append(
            LabelRide(
                start_s=item.start_s,
                end_s=item.end_s,
                acid_drop=item.acid_drop,
                origin=_origin(item),
            )
        )
    return SessionLabels(source=work.source, rides=sorted(rides, key=lambda r: r.start_s))


def fmt_time(seconds: float) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}" if h else f"{int(m):02d}:{s:05.2f}"


def parse_time(text: str) -> float:
    text = text.strip()
    if not re.fullmatch(r"\d+(:\d+){0,2}(\.\d+)?", text):
        raise LabelError(f"cannot read time {text!r}; use mm:ss.ss")
    seconds = 0.0
    for part in text.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds


def propose(rides: Rides, out_csv: Path) -> int:
    rows: list[dict[str, str]] = []
    spans = [(r.ride_id, r.start_s, r.end_s, r.start_kind, r.confidence) for r in rides.rides]
    spans += [(s.ride_id, s.start_s, s.end_s, "short", s.confidence) for s in rides.short_attempts]
    for rid, start, end, kind, conf in sorted(spans, key=lambda x: x[1]):
        rows.append(
            {
                "id": rid,
                "start": fmt_time(start),
                "end": fmt_time(end),
                "length_s": f"{end - start:.1f}",
                "detected_as": kind,
                "confidence": f"{conf:.2f}",
                "verdict": "?",
                "new_start": "",
                "new_end": "",
                "acid_drop": "yes" if kind == "acid_drop" else "",
                "notes": "",
            }
        )
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:  # BOM: Excel reads UTF-8
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def import_csv(path: Path, source: str) -> SessionLabels:
    labels: list[LabelRide] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for n, row in enumerate(csv.DictReader(f), start=2):
            verdict = (row.get("verdict") or "").strip().lower()
            if verdict in ("", "?"):
                raise LabelError(f"{path.name} line {n}: verdict not set (ok, fix, no or add)")
            if verdict == "no":
                continue
            acid = (row.get("acid_drop") or "").strip().lower() in ("yes", "y", "1", "true", "x")
            try:
                if verdict == "ok":
                    start, end = parse_time(row["start"]), parse_time(row["end"])
                    origin = "accepted"
                elif verdict in ("fix", "add"):
                    start = parse_time(row["new_start"] or row["start"])
                    end = parse_time(row["new_end"] or row["end"])
                    origin = "corrected" if verdict == "fix" else "added"
                else:
                    raise LabelError(f"unknown verdict {verdict!r}")
            except (KeyError, LabelError) as exc:
                raise LabelError(f"{path.name} line {n}: {exc}") from exc
            if end <= start:
                raise LabelError(f"{path.name} line {n}: end must be after start")
            labels.append(LabelRide(start_s=start, end_s=end, acid_drop=acid, origin=origin))
    return SessionLabels(source=source, rides=sorted(labels, key=lambda r: r.start_s))

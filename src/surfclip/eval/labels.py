"""Hand labels, proposed by the tool and validated by the user (research R15).

Workflow until the review UI's label mode exists (US4):

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

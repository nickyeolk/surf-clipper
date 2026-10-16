"""Evaluation marks for ride analysis (004 research R8).

The user marks, on their own rides, when each turn happened (and optionally pumps) and how the
ride ended. Marks are evaluation data only: they never change rides, edits or the analysis.
They hold times, never names, so they live with the other labels in ``labels/analysis``.
Rides are matched by time span, so marks survive ride edits and re-runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from surfclip.store.schemas import Riders, Rides

SCHEMA_VERSION = "1.0.0"
MATCH_IOU = 0.5
Ending = Literal["fall", "exit", "unclear"]


class MarkedRide(BaseModel):
    start_s: float
    end_s: float
    ride_id: str | None = None  # the ride it was marked on (a hint; spans are what count)
    turns: list[float] = Field(default_factory=list[float])
    pumps: list[float] = Field(default_factory=list[float])
    ending: Ending | None = None


class AnalysisMarks(BaseModel):
    schema_version: str = SCHEMA_VERSION
    source: str
    rides: list[MarkedRide] = Field(default_factory=list[MarkedRide])
    final: bool = False

    @property
    def remaining(self) -> int:
        return sum(1 for r in self.rides if r.ending is None)


def iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union > 0 else 0.0


class MarksError(ValueError):
    pass


def marks_path(labels_dir: Path, source_path: str) -> Path:
    return labels_dir / f"{Path(source_path).stem}.json"


def named_rides(rides: Rides, riders: Riders | None) -> list[str]:
    """Ride ids of riders the user named (the riders analysis is for)."""
    if riders is None:
        return []
    named = {r for g in riders.riders if g.name and not g.ignored for r in g.ride_ids}
    return [r.ride_id for r in sorted(rides.rides, key=lambda r: r.start_s) if r.ride_id in named]


def marks_work(
    existing: AnalysisMarks | None, rides: Rides, riders: Riders | None, source: str
) -> AnalysisMarks:
    """The marks to show: saved marks re-attached to the current rides, plus empty entries for
    named riders' rides not marked yet. Saved marks that match no current ride are kept."""
    by_id = {r.ride_id: r for r in rides.rides}
    wanted = [by_id[i] for i in named_rides(rides, riders)]
    saved = list(existing.rides) if existing else []
    out: list[MarkedRide] = []
    used: set[int] = set()
    for ride in wanted:
        span = (ride.start_s, ride.end_s)
        best, best_iou = None, MATCH_IOU
        for k, m in enumerate(saved):
            v = iou(span, (m.start_s, m.end_s))
            if k not in used and v >= best_iou:
                best, best_iou = k, v
        if best is None:
            out.append(MarkedRide(start_s=ride.start_s, end_s=ride.end_s, ride_id=ride.ride_id))
        else:
            used.add(best)
            out.append(saved[best].model_copy(update={"ride_id": ride.ride_id}))
    out += [m for k, m in enumerate(saved) if k not in used]
    out.sort(key=lambda m: m.start_s)
    return AnalysisMarks(source=source, rides=out, final=bool(existing and existing.final))


def finalize(marks: AnalysisMarks) -> AnalysisMarks:
    if not marks.rides:
        raise MarksError("no rides to mark: name yourself in Riders first")
    if marks.remaining:
        raise MarksError(f"{marks.remaining} rides still need an ending (fall, exit or unclear)")
    for m in marks.rides:
        outside = [t for t in m.turns + m.pumps if not m.start_s - 1 <= t <= m.end_s + 1]
        if outside:
            raise MarksError(f"marks at {outside} are outside the ride at {m.start_s:.1f} s")
    return marks.model_copy(update={"final": True})

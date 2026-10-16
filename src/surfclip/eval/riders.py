"""Rider labels and rider-assignment metrics (T010, T013; research R8).

Rider labels say who rode each labelled ride of 001 (``labels/rides/<video>.json``). They are
evaluation data only: they never change rides, rider edits or riders.json. Proposals come from
grouping the *detected* rides in memory, so labelling does not depend on the user's own review
edits (e.g. rides deleted in Review).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np
import scipy.optimize as _optimize  # pyright: ignore[reportMissingTypeStubs]
from pydantic import BaseModel, Field

from surfclip.config import Config
from surfclip.eval.labels import LabelError, SessionLabels
from surfclip.eval.metrics import Span, iou
from surfclip.riders.session import build_riders, describe_rides
from surfclip.store.schemas import Riders, Rides
from surfclip.store.session import SessionStore

optimize: Any = _optimize  # SciPy ships no type information

SCHEMA_VERSION = "1.0.0"
PROPOSE_IOU = 0.3  # a detected ride this close to a labelled ride proposes its group
MATCH_IOU = 0.5  # as SC-001 of 001


class RiderLabelItem(BaseModel):
    id: str  # L000.. in time order of the ride labels
    start_s: float
    end_s: float
    rider: str | None = None  # the user's answer
    proposed: str | None = None  # "Rider N" from the detected grouping
    detected_ride: str | None = None


class RiderLabelWork(BaseModel):
    schema_version: str = SCHEMA_VERSION
    source: str
    items: list[RiderLabelItem] = Field(default_factory=list[RiderLabelItem])
    named: list[str] = Field(default_factory=list[str])  # riders the user would name (e.g. "me")
    finalized: bool = False

    @property
    def remaining(self) -> int:
        return sum(1 for i in self.items if not i.rider)


class LabelledRide(BaseModel):
    start_s: float
    end_s: float
    rider: str


class RiderLabels(BaseModel):
    schema_version: str = SCHEMA_VERSION
    source: str
    named: list[str] = Field(default_factory=list[str])
    rides: list[LabelledRide] = Field(default_factory=list[LabelledRide])


def detected_grouping(store: SessionStore, config: Config) -> tuple[Rides, Riders]:
    """Group the detected rides (not the user's edited list) with the current settings."""
    from surfclip.stages import session_observations

    detected = store.read_model("rides.detected.json", Rides)
    app = describe_rides(store, detected.rides, session_observations(store), config.riders)
    riders = build_riders(
        store.session.session_id,
        detected.rides,
        app,
        config.riders,
        overlap_allowed_s=config.rides.changeover_overlap_max_s,
    )
    return detected, riders


def group_names(riders: Riders) -> dict[str, str]:
    """Ride id -> "Rider N" (groups numbered largest first, as in the UI)."""
    out: dict[str, str] = {}
    for k, g in enumerate(riders.riders, start=1):
        for r in g.ride_ids:
            out[r] = g.name or f"Rider {k}"
    return out


def propose_work(
    labels: SessionLabels, detected: Rides, riders: Riders, source: str
) -> RiderLabelWork:
    names = group_names(riders)
    items: list[RiderLabelItem] = []
    for k, lab in enumerate(sorted(labels.rides, key=lambda r: r.start_s)):
        best = max(
            detected.rides,
            key=lambda d: iou(Span(lab.start_s, lab.end_s), Span(d.start_s, d.end_s)),
            default=None,
        )
        close = (
            best is not None
            and iou(Span(lab.start_s, lab.end_s), Span(best.start_s, best.end_s)) >= PROPOSE_IOU
        )
        items.append(
            RiderLabelItem(
                id=f"L{k:03d}",
                start_s=lab.start_s,
                end_s=lab.end_s,
                proposed=names.get(best.ride_id) if close and best else None,
                detected_ride=best.ride_id if close and best else None,
            )
        )
    return RiderLabelWork(source=source, items=items)


def finalize(work: RiderLabelWork) -> RiderLabels:
    missing = [i.id for i in work.items if not i.rider]
    if missing:
        raise LabelError(f"{len(missing)} rides have no rider yet (first: {missing[0]})")
    return RiderLabels(
        source=work.source,
        named=work.named,
        rides=[
            LabelledRide(start_s=i.start_s, end_s=i.end_s, rider=i.rider or "") for i in work.items
        ],
    )


@dataclass
class RiderMetrics:
    labelled: int  # labelled rides matched to a detected ride
    unmatched: int  # labelled rides with no detected ride (001 misses: not scored here)
    correct: int  # in their true rider's group (one-to-one majority mapping)
    true_riders: int
    groups: int
    corrections: int = 0  # SC-002: same-as merges + single-ride moves for the named riders

    @property
    def accuracy(self) -> float:  # SC-001
        return self.correct / self.labelled if self.labelled else 0.0


def evaluate_riders(labels: RiderLabels, detected: Rides, riders: Riders) -> RiderMetrics:
    group_of = {r: g.rider_id for g in riders.riders for r in g.ride_ids}
    pairs: list[tuple[str, str]] = []
    rows: list[tuple[str, str, str]] = []  # ride, true rider, card
    unmatched = 0
    for lab in labels.rides:
        best = max(
            detected.rides,
            key=lambda d: iou(Span(lab.start_s, lab.end_s), Span(d.start_s, d.end_s)),
            default=None,
        )
        if (
            best is None
            or best.ride_id not in group_of
            or iou(Span(lab.start_s, lab.end_s), Span(best.start_s, best.end_s)) < MATCH_IOU
        ):
            unmatched += 1
            continue
        pairs.append((lab.rider, group_of[best.ride_id]))
        rows.append((best.ride_id, lab.rider, group_of[best.ride_id]))
    true = sorted({t for t, _ in pairs})
    pred = sorted({p for _, p in pairs})
    counts = Counter(pairs)
    table = np.array([[counts[(t, p)] for p in pred] for t in true], dtype=np.float64)
    correct = 0
    if table.size:
        ri, ci = optimize.linear_sum_assignment(-table)  # one group per true rider, most rides
        correct = int(table[ri, ci].sum())
    named = [n for n in labels.named if n in true]
    return RiderMetrics(
        len(pairs), unmatched, correct, len(true), len(pred), corrections(rows, named)
    )


def corrections(rows: list[tuple[str, str, str]], named: list[str]) -> int:
    """Actions needed to make every named rider's card exactly right with the Riders screen:
    one same-as per extra card holding only that rider, one move per stray ride."""
    merges = 0
    moved: set[str] = set()
    for who in named:
        cards = Counter(card for _, t, card in rows if t == who)
        main = cards.most_common(1)[0][0]
        for card in cards:
            if card == main:
                continue
            inside = [(r, t) for r, t, c in rows if c == card]
            if all(t == who for _, t in inside):
                merges += 1
            else:
                moved |= {r for r, t in inside if t == who}
        moved |= {r for r, t, c in rows if c == main and t != who}
    return merges + len(moved)

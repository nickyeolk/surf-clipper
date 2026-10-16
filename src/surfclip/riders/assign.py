"""Assign rides to riders with a confidence, and pick the review queue (research R5).

A ride's confidence is the margin between its distance to its own rider and to the nearest other
rider (centroids of the rides' descriptors): 1 when no other rider is close, 0 when another rider
is as close. The queue holds rides below ``queue_below`` that involve a *named* rider, either as
their own rider or as the nearest other one (clarification: unnamed riders are never queued).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
Distance = Callable[[FloatArray, FloatArray], float]
LOW_EVIDENCE_CAP = 0.3


@dataclass(frozen=True)
class Assigned:
    ride_id: str
    group: int  # index into the groups
    confidence: float
    runner_up: int | None  # nearest other group


def centroids(
    groups: Sequence[Sequence[str]], descriptors: Mapping[str, FloatArray]
) -> list[FloatArray]:
    return [np.mean([descriptors[r] for r in g], axis=0) for g in groups]


def assign_confidence(
    groups: Sequence[Sequence[str]],
    descriptors: Mapping[str, FloatArray],
    distance: Distance,
    low_evidence: set[str],
) -> list[Assigned]:
    cents = centroids(groups, descriptors)
    out: list[Assigned] = []
    for gi, group in enumerate(groups):
        for ride in group:
            own = distance(descriptors[ride], cents[gi])
            others = [(distance(descriptors[ride], c), k) for k, c in enumerate(cents) if k != gi]
            if not others:
                conf, runner = 1.0, None
            else:
                d2, runner = min(others)
                conf = float(np.clip((d2 - own) / max(d2, 1e-9), 0.0, 1.0))
            if ride in low_evidence:
                conf = min(conf, LOW_EVIDENCE_CAP)
            out.append(Assigned(ride, gi, round(conf, 3), runner))
    return out


def queue(
    assigned: Sequence[Assigned], named_groups: set[int], below: float, fixed: set[str]
) -> list[str]:
    """Ride ids to ask about, lowest confidence first."""
    picks = [
        a
        for a in assigned
        if a.ride_id not in fixed
        and a.confidence < below
        and (a.group in named_groups or (a.runner_up is not None and a.runner_up in named_groups))
    ]
    return [a.ride_id for a in sorted(picks, key=lambda a: a.confidence)]

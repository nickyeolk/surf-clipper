"""Evaluation against hand labels (constitution II; SC-001..SC-003).

Detected and labelled rides are matched one-to-one, best time-IoU first, with IoU >= 0.5.
Recall counts only labels at least ``min_length_s`` long; precision counts every detected ride.
Start errors of acid-drop rides are reported separately, as the spec requires.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, NamedTuple

import numpy as np
from pydantic import BaseModel, ConfigDict

IOU_MATCH = 0.5


class Span(NamedTuple):
    start_s: float
    end_s: float


class LabelRide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_s: float
    end_s: float
    acid_drop: bool = False
    origin: Literal["accepted", "corrected", "added"] | None = None


@dataclass
class Metrics:
    n_labels: int
    n_detected: int
    recall: float
    precision: float
    missed: list[int] = field(default_factory=list[int])  # indices into labels
    false_rides: list[int] = field(default_factory=list[int])  # indices into detected
    start_err_median: float = 0.0
    start_err_p95: float = 0.0
    end_err_median: float = 0.0
    end_err_p95: float = 0.0
    acid_start_errs: list[float] = field(default_factory=list[float])


def iou(a: Span, b: Span) -> float:
    inter = max(0.0, min(a.end_s, b.end_s) - max(a.start_s, b.start_s))
    union = max(a.end_s, b.end_s) - min(a.start_s, b.start_s)
    return inter / union if union > 0 else 0.0


def _stats(errs: list[float]) -> tuple[float, float]:
    if not errs:
        return 0.0, 0.0
    arr = np.array(errs, dtype=np.float64)
    return float(np.median(arr)), float(np.percentile(arr, 95, method="higher"))


def evaluate(
    detected: Sequence[Span], labels: Sequence[LabelRide], *, min_length_s: float = 0.0
) -> Metrics:
    pairs = sorted(
        (
            (iou(d, Span(lab.start_s, lab.end_s)), di, li)
            for di, d in enumerate(detected)
            for li, lab in enumerate(labels)
        ),
        reverse=True,
    )
    matched: dict[int, int] = {}  # label index -> detected index
    used: set[int] = set()
    for score, di, li in pairs:
        if score < IOU_MATCH:
            break
        if li in matched or di in used:
            continue
        matched[li] = di
        used.add(di)

    eligible = [i for i, lab in enumerate(labels) if lab.end_s - lab.start_s >= min_length_s]
    missed = [i for i in eligible if i not in matched]
    false_rides = [i for i in range(len(detected)) if i not in used]

    start_errs: list[float] = []
    end_errs: list[float] = []
    acid: list[float] = []
    for li, di in sorted(matched.items()):
        lab, det = labels[li], detected[di]
        s_err = abs(det.start_s - lab.start_s)
        (acid if lab.acid_drop else start_errs).append(s_err)
        end_errs.append(abs(det.end_s - lab.end_s))

    s_med, s_p95 = _stats(start_errs)
    e_med, e_p95 = _stats(end_errs)
    return Metrics(
        n_labels=len(eligible),
        n_detected=len(detected),
        recall=(len(eligible) - len(missed)) / len(eligible) if eligible else 1.0,
        precision=len(used) / len(detected) if detected else 1.0,
        missed=missed,
        false_rides=false_rides,
        start_err_median=s_med,
        start_err_p95=s_p95,
        end_err_median=e_med,
        end_err_p95=e_p95,
        acid_start_errs=acid,
    )

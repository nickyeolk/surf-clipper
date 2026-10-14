"""Assemble per-track rides into session rides (FR-012, FR-014, FR-015, FR-018, FR-019).

* Acid drops across tracks: a track that ends on an entry side wall, followed within
  ``acid_link_s`` by an on-wave track starting nearby (in rider heights), is one ride that starts
  at the jump. The tracker often loses a fast, blurred drop-in.
* Frame-edge returns: a ride that leaves through a frame edge and comes back through the same edge
  within ``frame_edge_grace_s`` continues as one ride.
* Lessons: a ride is flagged when other people are in the zone (an instructor in the water, or
  other beginners holding the same pole, as on 20241004) for at least ``lesson_overlap_frac`` of
  it. A changeover overlap of a second or two is not a lesson.
* Rides shorter than ``min_length_s`` become short attempts. Clips get padding, clamped to the
  video.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from surfclip.config import RidesConfig
from surfclip.rides.evidence import Evidence
from surfclip.rides.state_machine import StartKind, TrackRide
from surfclip.store.schemas import Ride, RideFlags, RideState, ShortAttempt

_EPS = 1e-6


@dataclass
class _Draft:
    start_t: float
    end_t: float
    run_start_t: float
    start_kind: StartKind
    track_ids: list[int]
    first_ev: Evidence  # first on-wave evidence (where the rider was when the run began)
    last_ev: Evidence
    evidence: list[Evidence] = field(default_factory=list[Evidence])
    lesson: bool = False


def _merge_lessons(drafts: list[_Draft], cfg: RidesConfig) -> list[_Draft]:
    """A lesson is one ride (user decision 2026-10-15): beginners overlapping on the wave are
    merged into a single ride spanning the whole lesson, flagged "lesson". A ride joins a lesson
    when either is a lesson ride and they overlap by more than a changeover."""
    merged: list[_Draft] = []
    for d in sorted(drafts, key=lambda x: x.start_t):
        prev = merged[-1] if merged else None
        overlap = (min(prev.end_t, d.end_t) - d.start_t) if prev else 0.0
        if (
            prev is not None
            and (prev.lesson or d.lesson)
            and (
                overlap > cfg.changeover_overlap_max_s or (prev.lesson and d.lesson and overlap > 0)
            )
        ):
            if d.end_t > prev.end_t:
                prev.end_t, prev.last_ev = d.end_t, d.last_ev
            prev.track_ids += [t for t in d.track_ids if t not in prev.track_ids]
            prev.evidence += d.evidence
            prev.lesson = True
            continue
        merged.append(d)
    return merged


def _draft(tr: TrackRide) -> _Draft:
    return _Draft(
        start_t=tr.start_t,
        end_t=tr.end_t,
        run_start_t=tr.run_start_t,
        start_kind=tr.start_kind,
        track_ids=[tr.track_id],
        first_ev=tr.start_ev,
        last_ev=tr.last_ev,
        evidence=list(tr.evidence),
    )


def _link_acid_drops(
    drafts: list[_Draft], evidence: Mapping[int, Sequence[Evidence]], cfg: RidesConfig
) -> None:
    for d in drafts:
        if d.start_kind == "acid_drop":
            continue
        best: tuple[float, Evidence] | None = None
        for tid, evs in evidence.items():
            if tid in d.track_ids or not evs:
                continue
            last = evs[-1]
            gap = d.run_start_t - last.t
            if last.region != "side_wall" or not (0 <= gap <= cfg.acid_link_s + _EPS):
                continue
            fx, fy = last.obs.feet
            gx, gy = d.first_ev.obs.feet
            dist = math.hypot(gx - fx, gy - fy) / max(last.obs.box_height, 1.0)
            if dist <= cfg.acid_link_heights and (best is None or dist < best[0]):
                best = (dist, last)
        if best is not None:
            wall_ev = best[1]
            d.start_t = wall_ev.t
            d.start_kind = "acid_drop"
            d.track_ids.insert(0, wall_ev.obs.track_id)
            d.evidence.insert(0, wall_ev)


def _merge_edge_returns(drafts: list[_Draft], cfg: RidesConfig) -> list[_Draft]:
    drafts = sorted(drafts, key=lambda d: d.start_t)
    merged: list[_Draft] = []
    for d in drafts:
        prev = merged[-1] if merged else None
        edge = prev.last_ev.obs.edge if prev else "none"
        if (
            prev is not None
            and edge != "none"
            and d.first_ev.obs.edge == edge
            and 0 <= d.start_t - prev.end_t <= cfg.frame_edge_grace_s + _EPS
        ):
            prev.end_t = max(prev.end_t, d.end_t)
            prev.last_ev = d.last_ev
            prev.track_ids += [t for t in d.track_ids if t not in prev.track_ids]
            prev.evidence += d.evidence
            continue
        merged.append(d)
    return merged


def _merge_continuations(drafts: list[_Draft], cfg: RidesConfig) -> list[_Draft]:
    """Join a ride with an unexplained start to one that ended just before, at the same spot.

    The tracker sometimes hands a rider to another track id mid-ride, and stitching refuses
    because that id already existed (20240924 28:04). Thresholds are the stitching ones.
    """
    drafts = sorted(drafts, key=lambda d: d.start_t)
    merged: list[_Draft] = []
    for d in drafts:
        prev = max(merged, key=lambda p: p.end_t, default=None)
        if prev is not None and d.start_kind == "unknown":
            gap = d.start_t - prev.end_t
            a, b = prev.last_ev.obs, d.first_ev.obs
            height = max(a.box_height, b.box_height, 1.0)
            dist = math.hypot(b.feet[0] - a.feet[0], b.feet[1] - a.feet[1]) / height
            near = dist <= cfg.stitch_base_heights + cfg.stitch_heights_per_s * max(gap, 0.0)
            if -0.2 <= gap <= cfg.stitch_gap_s + _EPS and near:
                prev.end_t = max(prev.end_t, d.end_t)
                prev.last_ev = d.last_ev
                prev.track_ids += [t for t in d.track_ids if t not in prev.track_ids]
                prev.evidence += d.evidence
                continue
        merged.append(d)
    return merged


def _lesson(d: _Draft, evidence: Mapping[int, Sequence[Evidence]], cfg: RidesConfig) -> bool:
    duration = d.end_t - d.start_t
    if duration <= 0:
        return False
    times = {
        round(ev.t, 3)
        for tid, evs in evidence.items()
        if tid not in d.track_ids
        for ev in evs
        # Anyone else in the zone: an instructor in the water, or other beginners on the pole.
        if d.start_t <= ev.t <= d.end_t and ev.region == "zone"
    }
    if not times:
        return False
    steps = sorted(times)
    step = min((b - a for a, b in itertools.pairwise(steps)), default=0.2)
    return len(times) * step >= cfg.lesson_overlap_frac * duration


def _confidence(d: _Draft) -> float:
    on = [ev for ev in d.evidence if d.run_start_t - _EPS <= ev.t <= d.end_t + _EPS]
    if not on:
        return 0.0
    cands = [ev for ev in on if ev.candidate]
    if not cands:
        return 0.0
    mean_score = sum(ev.obs.score for ev in cands) / len(cands)
    return max(0.0, min(1.0, mean_score * len(cands) / len(on)))


def _timeline(d: _Draft) -> list[tuple[float, RideState]]:
    tl: list[tuple[float, RideState]] = []
    if d.start_t < d.run_start_t - _EPS:
        tl.append((round(d.start_t, 3), "dropping_in"))
    tl.append((round(d.run_start_t, 3), "on_wave"))
    tl.append((round(d.end_t, 3), "off"))
    return tl


def assemble(
    track_rides: Sequence[TrackRide],
    evidence: Mapping[int, Sequence[Evidence]],
    *,
    cfg: RidesConfig,
    fps: float,
    duration_s: float,
) -> tuple[list[Ride], list[ShortAttempt]]:
    drafts = [_draft(tr) for tr in track_rides]
    _link_acid_drops(drafts, evidence, cfg)
    drafts = _merge_edge_returns(drafts, cfg)
    drafts = _merge_continuations(drafts, cfg)
    for d in drafts:
        d.lesson = _lesson(d, evidence, cfg)
    drafts = _merge_lessons(drafts, cfg)

    rides: list[Ride] = []
    short: list[ShortAttempt] = []
    used_ids: set[str] = set()
    for d in sorted(drafts, key=lambda x: x.start_t):
        if d.end_t <= d.start_t:
            continue
        start_frame = round(d.start_t * fps)
        base = f"r{start_frame:06d}"
        rid = base
        n = 1
        while rid in used_ids:
            rid = f"{base}_{n}"
            n += 1
        used_ids.add(rid)
        confidence = _confidence(d)
        if d.end_t - d.start_t < cfg.min_length_s - _EPS:
            short.append(
                ShortAttempt(
                    ride_id="s" + rid[1:],
                    start_s=d.start_t,
                    end_s=d.end_t,
                    confidence=confidence,
                )
            )
            continue
        rides.append(
            Ride(
                ride_id=rid,
                start_s=d.start_t,
                end_s=d.end_t,
                confidence=confidence,
                start_frame=start_frame,
                end_frame=round(d.end_t * fps),
                clip_start_s=max(0.0, d.start_t - cfg.pad_before_s),
                clip_end_s=min(duration_s, d.end_t + cfg.pad_after_s),
                epochs=[0],
                track_ids=d.track_ids,
                start_kind=d.start_kind,
                state_timeline=_timeline(d),
                flags=RideFlags(
                    lesson=d.lesson,
                    truncated=any(ev.obs.edge != "none" for ev in d.evidence),
                ),
            )
        )
    return rides, short

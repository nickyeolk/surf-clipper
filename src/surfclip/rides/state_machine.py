"""Per-track on/off-wave state machine (FR-010, FR-011; constitution V "confirm late, start early").

A *run* is a stretch of riding-candidate frames whose gaps are no longer than
``evidence_gap_s`` (spray and blur briefly hide the board). A run becomes a ride once it has
lasted ``confirm_window_s`` while moving along the wave at ``min_lateral_speed_pool`` or more.
Its start is then back-dated:

* to the last frame on an entry side wall, if the rider left it within ``acid_link_s``
  (``acid_drop``);
* to the track's first appearance, if that was at the frame edge (``off_frame``: the entry wall
  is out of shot);
* otherwise to the run's first frame.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import median
from typing import Literal

from surfclip.config import RidesConfig
from surfclip.rides.evidence import Evidence
from surfclip.store.schemas import RideState

StartKind = Literal["step_in", "acid_drop", "off_frame", "unknown"]
_EPS = 1e-6


@dataclass
class TrackRide:
    track_id: int
    start_t: float
    end_t: float
    run_start_t: float
    confirmed_t: float
    start_kind: StartKind
    start_ev: Evidence  # evidence at the (back-dated) start
    first_run_ev: Evidence
    last_ev: Evidence
    evidence: list[Evidence] = field(default_factory=list[Evidence])


def _frame_step(evs: Sequence[Evidence]) -> float:
    diffs = [b.t - a.t for a, b in itertools.pairwise(evs) if b.t > a.t]
    return median(diffs) if diffs else 0.0


def _still_riding(ev: Evidence, cfg: RidesConfig) -> bool:
    """Plausibly still riding without full evidence: on the face or against a side wall, and
    upright, on the board, or stalled against a side wall in any posture (a hand on the wall,
    a deep crouch the box shape reads as "sitting", sitting back against the wall; all seen
    on 20240924). Not gone behind the wave."""
    in_pool = ev.region == "side_wall" or (ev.region == "zone" and ev.on_face)
    at_wall = ev.u <= cfg.wall_stall_pool or ev.u >= 1 - cfg.wall_stall_pool
    return in_pool and (ev.obs.stance in ("standing", "crouched") or ev.obs.board or at_wall)


def _down_time(evs: Sequence[Evidence], a: int, b: int, step: float, cfg: RidesConfig) -> float:
    """Time between frames a and b that looks like being down: frames that are not still
    riding, plus stretches with no detection at all."""
    down = 0.0
    for k in range(a, b):
        nxt = evs[k + 1]
        down += max(0.0, nxt.t - evs[k].t - step)  # not detected
        if k + 1 < b and not _still_riding(nxt, cfg):
            down += step
    return down


def _wall_stall(evs: Sequence[Evidence], a: int, b: int, step: float, cfg: RidesConfig) -> bool:
    """Every frame between a and b is the rider holding on at a side wall (20241004: crouched
    against the wall for ~5 s, then riding on). Sitting without a board is waiting on the wall,
    not a stall; that, or not being seen, may add up to at most the evidence gap."""
    between = evs[a + 1 : b]
    if not between:
        return False
    down = sum(max(0.0, evs[k + 1].t - evs[k].t - step) for k in range(a, b))
    for ev in between:
        at_wall = ev.u <= cfg.wall_stall_pool or ev.u >= 1 - cfg.wall_stall_pool
        if not (at_wall and ev.region in ("zone", "side_wall")):
            return False
        if not (ev.obs.stance in ("standing", "crouched") or ev.obs.board):
            down += step
    return down <= cfg.evidence_gap_s + _EPS


def _runs(evs: Sequence[Evidence], cfg: RidesConfig, step: float) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start = last = -1
    for i, ev in enumerate(evs):
        if not (ev.candidate or (start >= 0 and ev.continues)):
            continue
        gap = ev.t - evs[last].t - step if start >= 0 else float("inf")
        bridged = (
            gap <= cfg.upright_bridge_s + _EPS
            and _down_time(evs, last, i, step, cfg) <= cfg.evidence_gap_s + _EPS
        ) or (gap <= cfg.wall_stall_max_s + _EPS and _wall_stall(evs, last, i, step, cfg))
        if start >= 0 and (gap <= cfg.evidence_gap_s + _EPS or bridged):
            last = i
            continue
        if start >= 0:
            runs.append((start, last))
        start = last = i
    if start >= 0:
        runs.append((start, last))
    return runs


def _confirmed_index(evs: Sequence[Evidence], i0: int, i1: int, cfg: RidesConfig) -> int | None:
    path = 0.0
    prev_u = evs[i0].u
    for k in range(i0, i1 + 1):
        if evs[k].candidate:
            path += abs(evs[k].u - prev_u)
            prev_u = evs[k].u
        elapsed = evs[k].t - evs[i0].t
        if elapsed + _EPS >= cfg.confirm_window_s and path / elapsed >= cfg.min_lateral_speed_pool:
            return k
    return None


def _back_date(evs: Sequence[Evidence], i0: int, cfg: RidesConfig) -> tuple[int, StartKind]:
    run_t = evs[i0].t
    for j in range(i0 - 1, -1, -1):
        if run_t - evs[j].t > cfg.acid_link_s + _EPS:
            break
        if evs[j].region == "side_wall":
            return j, "acid_drop"
    if evs[0].obs.edge != "none" and run_t - evs[0].t <= cfg.acid_link_s + _EPS:
        return 0, "off_frame"
    return i0, "unknown"


def track_rides(
    evs: Sequence[Evidence], cfg: RidesConfig
) -> tuple[list[RideState], list[TrackRide]]:
    """States per evidence frame, and the confirmed rides of one track."""
    states: list[RideState] = ["off"] * len(evs)
    rides: list[TrackRide] = []
    step = _frame_step(evs)
    for i0, i1 in _runs(evs, cfg, step):
        k = _confirmed_index(evs, i0, i1, cfg)
        if k is None:
            for i in range(i0, i1 + 1):
                states[i] = "dropping_in"
            continue
        s, kind = _back_date(evs, i0, cfg)
        for i in range(s, i0):
            states[i] = "dropping_in"
        for i in range(i0, i1 + 1):
            states[i] = "on_wave"
        rides.append(
            TrackRide(
                track_id=evs[i0].obs.track_id,
                start_t=evs[s].t,
                end_t=evs[i1].t,
                run_start_t=evs[i0].t,
                confirmed_t=evs[k].t,
                start_kind=kind,
                start_ev=evs[s],
                first_run_ev=evs[i0],
                last_ev=evs[i1],
                evidence=list(evs[s : i1 + 1]),
            )
        )
    return states, rides

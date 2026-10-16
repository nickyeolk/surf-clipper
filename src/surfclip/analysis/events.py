"""Turns, pumps, trimming and the ride's ending (004 research R4, R5).

First version, rules only (constitution VIII); thresholds are tuned on the user's marks (T012).

* A **turn** is a compression minimum below ``pump_depth`` with a change of direction within
  ``turn_window_s``: the lateral pool velocity changes sign at speed, or the rider's body
  rotation (shoulder line) flips. Without either, the minimum is a **pump**.
* **Trimming** is riding time outside turn and pump windows; **unclear** time is left out.
* The **ending** looks at the last ``fall_window_s``: a crouch collapse or a body lying over is
  a fall; an upright body (or feet leaving over a side wall) is an exit.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import signal as _signal  # pyright: ignore[reportMissingTypeStubs]

from surfclip.analysis.pose import Keypoints
from surfclip.analysis.signals import (
    L_ANK,
    L_SH,
    R_ANK,
    R_SH,
    compression,
    smooth,
    smooth_rotation,
    unclear_mask,
)
from surfclip.config import AnalysisPoseConfig, Config
from surfclip.edits.log import confirmed_zone, read_edits
from surfclip.store.schemas import (
    AnalysisEvent,
    Ending,
    Ride,
    RideAnalysis,
    RideShares,
    RideSummary,
)
from surfclip.store.session import SessionStore
from surfclip.zone.geometry import PoolMapping

FloatArray = np.ndarray[Any, np.dtype[np.float64]]
sp_signal: Any = _signal  # SciPy ships no type information
TURN_HALF_S = 0.6  # time around a turn counted as turning
PUMP_HALF_S = 0.4
EDGE_U = 0.06  # feet this close to a side wall (pool u) at the end = left over the wall
ROTATION_MIN = 0.15  # |shoulder width / torso| on both sides of a rotation flip


def lateral(store: SessionStore, kp: Keypoints, cfg: AnalysisPoseConfig) -> FloatArray:
    """Feet across the wave (pool u) where the session has a confirmed zone, else NaN."""
    zone = confirmed_zone(read_edits(store))
    n = len(kp)
    if zone is None or n == 0:
        return np.full(n, np.nan)
    feet = (kp.kp[:, L_ANK, :2] + kp.kp[:, R_ANK, :2]) / 2
    ok = np.isfinite(feet).all(axis=1)
    u = np.full(n, np.nan)
    if ok.any():
        u[ok] = PoolMapping.from_corners(zone.corners).to_pool(feet[ok])[:, 0]
    u[(u < -0.5) | (u > 1.5)] = np.nan  # off the pool plane: not a usable position
    return smooth(u, np.isfinite(u) & ~unclear_mask(kp, cfg), cfg.fps, cfg.smooth_s)


def direction_change(series: FloatArray, i: int, half: int, min_speed: float, fps: float) -> bool:
    """Does the series' slope change sign around index i, at speed on both sides?"""
    lo, hi = max(0, i - half), min(len(series) - 1, i + half)
    if hi - lo < 4:
        return False
    v = np.gradient(series[lo : hi + 1]) * fps
    v = v[np.isfinite(v)]
    if len(v) < 4:
        return False
    k = len(v) // 2
    before, after = np.nanmedian(v[:k]), np.nanmedian(v[k:])
    return bool(before * after < 0 and min(abs(before), abs(after)) >= min_speed)


def sign_flip(series: FloatArray, i: int, half: int, min_abs: float) -> bool:
    """Does the series itself change sign around index i (e.g. shoulders swinging from facing
    the camera to facing away), clearly on both sides?"""
    lo, hi = max(0, i - half), min(len(series), i + half + 1)
    before, after = series[lo:i], series[i + 1 : hi]
    before, after = before[np.isfinite(before)], after[np.isfinite(after)]
    if len(before) < 2 or len(after) < 2:
        return False
    b, a = float(np.median(before)), float(np.median(after))
    return b * a < 0 and min(abs(b), abs(a)) >= min_abs


def find_events(
    comp: FloatArray, lat: FloatArray, rot: FloatArray, cfg: AnalysisPoseConfig, t0: float
) -> tuple[list[AnalysisEvent], list[AnalysisEvent]]:
    fps = cfg.fps
    if not np.isfinite(comp).any():
        return [], []
    filled = np.where(np.isfinite(comp), comp, np.nanmax(comp))
    found: Any = sp_signal.find_peaks(
        -filled, height=-cfg.pump_depth, distance=max(1, int(0.6 * fps))
    )
    minima = [int(m) for m in found[0]]
    half = int(cfg.turn_window_s * fps)
    turns: list[AnalysisEvent] = []
    pumps: list[AnalysisEvent] = []
    for i in minima:
        if not np.isfinite(comp[i]):
            continue
        ev = AnalysisEvent(t=round(t0 + i / fps, 3), depth=round(float(comp[i]), 3))
        turned = (
            np.isfinite(lat).sum() > half
            and direction_change(lat, i, half, cfg.turn_speed_pool_per_s, fps)
        ) or sign_flip(rot, i, half, ROTATION_MIN)
        (turns if turned else pumps).append(ev)
    return turns, pumps


def shares(n: int, unclear: np.ndarray[Any, np.dtype[np.bool_]], turns: list[AnalysisEvent],
           pumps: list[AnalysisEvent], fps: float, t0: float) -> RideShares:  # fmt: skip
    if n == 0:
        return RideShares()
    state = np.zeros(n, dtype=int)  # 0 trimming, 1 pumping, 2 turning
    for evs, half, code in ((pumps, PUMP_HALF_S, 1), (turns, TURN_HALF_S, 2)):
        for e in evs:
            i = int(round((e.t - t0) * fps))
            lo, hi = max(0, i - int(half * fps)), min(n, i + int(half * fps) + 1)
            state[lo:hi] = np.maximum(state[lo:hi], code)
    clear = ~unclear

    def share(code: int) -> float:
        return round(float(np.count_nonzero(clear & (state == code))) / n, 3)

    return RideShares(
        turning=share(2),
        pumping=share(1),
        trimming=share(0),
        unclear=round(float(np.count_nonzero(unclear)) / n, 3),
    )


def body_tilt_deg(kp: Keypoints) -> FloatArray:
    """Angle of the shoulders->ankles line from the image vertical (lying over = large)."""
    sh = (kp.kp[:, L_SH, :2] + kp.kp[:, R_SH, :2]) / 2
    an = (kp.kp[:, L_ANK, :2] + kp.kp[:, R_ANK, :2]) / 2
    d = an - sh
    return np.degrees(np.arctan2(np.abs(d[:, 0]), np.abs(d[:, 1])))


def ending(comp: FloatArray, lat: FloatArray, tilt: FloatArray,
           unclear: np.ndarray[Any, np.dtype[np.bool_]], cfg: AnalysisPoseConfig) -> Ending:  # fmt: skip
    k = max(3, int(cfg.fall_window_s * cfg.fps))
    c_end, t_end, u_end = comp[-k:], tilt[-k:], lat[-k:]
    seen = np.isfinite(c_end) & ~unclear[-k:]
    if seen.sum() < 3:
        return "unclear"
    depth = float(np.nanmin(c_end[seen]))
    lean = float(np.nanmedian(t_end[seen]))
    if lean > 50 or depth < cfg.fall_depth:
        return "fall"
    last_u = u_end[np.isfinite(u_end)]
    if len(last_u) and (last_u[-1] < EDGE_U or last_u[-1] > 1 - EDGE_U):
        return "exit"
    if lean < 30 and float(np.nanmedian(c_end[seen])) >= 0.85:
        return "exit"
    return "unclear"


def analyse_ride(store: SessionStore, ride: Ride, kp: Keypoints, cfg: Config, *, rider: str,
                 cache_key: str, keypoints_key: str) -> RideAnalysis:  # fmt: skip
    p = cfg.analysis_pose
    t0 = float(kp.t[0]) if len(kp) else ride.start_s
    unclear = unclear_mask(kp, p) if len(kp) else np.zeros(0, dtype=bool)
    comp = compression(kp, p) if len(kp) else np.zeros(0)
    lat = lateral(store, kp, p)
    rot = smooth_rotation(kp, p) if len(kp) else np.zeros(0)
    turns, pumps = find_events(comp, lat, rot, p, t0)
    end = ending(comp, lat, body_tilt_deg(kp), unclear, p) if len(kp) else "unclear"
    events = sorted(e.t for e in turns + pumps)
    gaps = np.diff(events)
    depths = [e.depth for e in turns + pumps if e.depth is not None]
    summary = RideSummary(
        length_s=round(ride.length_s, 3),
        turns=len(turns),
        pumps=len(pumps),
        turn_rate_per_10s=round(10 * len(turns) / max(ride.length_s, 1e-6), 2),
        rhythm_cv=round(float(np.std(gaps) / np.mean(gaps)), 3) if len(gaps) >= 2 else None,
        mean_depth=round(float(np.mean(depths)), 3) if depths else None,
    )

    def rounded(a: FloatArray) -> list[float | None]:
        return [round(float(x), 3) if np.isfinite(x) else None for x in a]

    return RideAnalysis(
        ride_id=ride.ride_id,
        span=(round(ride.start_s, 3), round(ride.end_s, 3)),
        rider=rider,
        cache_key=cache_key,
        keypoints_key=keypoints_key,
        fps=p.fps,
        t0=round(t0, 3),
        compression=rounded(comp),
        lateral=rounded(lat),
        turns=turns,
        pumps=pumps,
        shares=shares(len(kp), unclear, turns, pumps, p.fps, t0),
        ending=end,
        ending_auto=end,
        summary=summary,
    )

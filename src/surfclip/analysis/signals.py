"""Signals from keypoints (004 research R2-R4). Every signal is a ratio of body segments in the
same frame, so zoom and distance from the camera cancel out (FR-002); nothing uses absolute
pixel sizes or joint angles.

* compression: how folded the rider is, 1.0 = their median in this ride, lower = more crouched
  - ``leg_torso``: hip-ankle distance / shoulder-hip distance
  - ``leg_straightness``: hip-ankle distance / (hip-knee + knee-ankle): 1 = straight legs;
    unaffected by how the torso leans
* rotation: signed shoulder width / torso length; changes sign when the rider turns from facing
  the camera to facing away (a cue for turns where the pool position is not usable)
* lateral: the feet across the wave in pool units (``u``), when the session has a zone
* unclear: frames where the needed joints are not seen or another person overlaps the crop
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import signal as _signal  # pyright: ignore[reportMissingTypeStubs]

from surfclip.analysis.pose import Keypoints
from surfclip.config import AnalysisPoseConfig

FloatArray = np.ndarray[Any, np.dtype[np.float64]]
sp_signal: Any = _signal  # SciPy ships no type information
L_SH, R_SH, L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANK, R_ANK = 5, 6, 11, 12, 13, 14, 15, 16


def _mid(kp: FloatArray, a: int, b: int) -> FloatArray:
    return (kp[:, a, :2] + kp[:, b, :2]) / 2


def _dist(p: FloatArray, q: FloatArray) -> FloatArray:
    return np.linalg.norm(p - q, axis=1)


def unclear_mask(kp: Keypoints, cfg: AnalysisPoseConfig) -> np.ndarray[Any, np.dtype[np.bool_]]:
    need = [L_SH, R_SH, L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANK, R_ANK]
    conf = kp.kp[:, need, 2]
    low = np.isnan(conf).any(axis=1) | (np.nan_to_num(conf, nan=0.0).min(axis=1) < cfg.min_conf)
    return low | (kp.other_iou > cfg.other_iou_max)


def raw_compression(kp: Keypoints, signal: str) -> FloatArray:
    k = kp.kp
    hip, ank, sh = _mid(k, L_HIP, R_HIP), _mid(k, L_ANK, R_ANK), _mid(k, L_SH, R_SH)
    leg = _dist(hip, ank)
    if signal == "leg_torso":
        torso = _dist(sh, hip)
        return np.where(torso > 1e-6, leg / np.maximum(torso, 1e-6), np.nan)
    if signal == "leg_straightness":
        path = (
            _dist(k[:, L_HIP, :2], k[:, L_KNEE, :2])
            + _dist(k[:, L_KNEE, :2], k[:, L_ANK, :2])
            + _dist(k[:, R_HIP, :2], k[:, R_KNEE, :2])
            + _dist(k[:, R_KNEE, :2], k[:, R_ANK, :2])
        ) / 2
        return np.where(path > 1e-6, leg / np.maximum(path, 1e-6), np.nan)
    raise ValueError(f"unknown compression signal {signal}")


def rotation(kp: Keypoints) -> FloatArray:
    k = kp.kp
    torso = _dist(_mid(k, L_SH, R_SH), _mid(k, L_HIP, R_HIP))
    return (k[:, L_SH, 0] - k[:, R_SH, 0]) / np.maximum(torso, 1e-6)


def smooth(
    values: FloatArray,
    valid: np.ndarray[Any, np.dtype[np.bool_]],
    fps: float,
    window_s: float,
    max_gap_s: float = 0.5,
) -> FloatArray:
    """Fill gaps up to max_gap_s by interpolation, smooth (Savitzky-Golay), NaN elsewhere."""
    v = np.where(valid & np.isfinite(values), values, np.nan)
    n = len(v)
    out = np.full(n, np.nan)
    good = np.flatnonzero(np.isfinite(v))
    if len(good) < 3:
        return out
    idx = np.arange(n)
    filled = np.interp(idx, good, v[good])
    # gap length at each frame: distance to the nearest valid frame on both sides
    prev = np.maximum.accumulate(np.where(np.isfinite(v), idx, -(10**9)))
    nxt = np.minimum.accumulate(np.where(np.isfinite(v), idx, 10**9)[::-1])[::-1]
    gap_ok = (nxt - prev) <= max_gap_s * fps + 1
    win = max(5, round(window_s * fps) | 1)
    if n >= win:
        filled = np.asarray(sp_signal.savgol_filter(filled, win, 2), dtype=float)
    out[gap_ok] = filled[gap_ok]
    return out


def compression(kp: Keypoints, cfg: AnalysisPoseConfig) -> FloatArray:
    """Smoothed compression, normalised so the ride's median is 1.0; NaN where unclear."""
    valid = ~unclear_mask(kp, cfg)
    s = smooth(raw_compression(kp, cfg.signal), valid, cfg.fps, cfg.smooth_s)
    med = np.nanmedian(s) if np.isfinite(s).any() else np.nan
    return s / med if np.isfinite(med) and med > 0 else s


def smooth_rotation(kp: Keypoints, cfg: AnalysisPoseConfig) -> FloatArray:
    valid = ~unclear_mask(kp, cfg)
    return smooth(rotation(kp), valid, cfg.fps, cfg.smooth_s)


L_WRIST, R_WRIST = 9, 10


def _torso(k: FloatArray) -> FloatArray:
    return _dist(_mid(k, L_SH, R_SH), _mid(k, L_HIP, R_HIP))


def raw_lean(kp: Keypoints) -> FloatArray:
    """Signed angle (degrees) of the hip->shoulder line from the image's vertical: 0 = upright,
    positive = leaning toward image right. Camera-relative (FR-002)."""
    d = _mid(kp.kp, L_SH, R_SH) - _mid(kp.kp, L_HIP, R_HIP)
    return np.degrees(np.arctan2(d[:, 0], -d[:, 1]))


def raw_arms(kp: Keypoints) -> FloatArray:
    """Wrist-to-wrist distance in torso lengths."""
    k = kp.kp
    return _dist(k[:, L_WRIST, :2], k[:, R_WRIST, :2]) / np.maximum(_torso(k), 1e-6)


def raw_stance(kp: Keypoints) -> FloatArray:
    """Ankle-to-ankle distance in torso lengths."""
    k = kp.kp
    return _dist(k[:, L_ANK, :2], k[:, R_ANK, :2]) / np.maximum(_torso(k), 1e-6)


def measures(kp: Keypoints, cfg: AnalysisPoseConfig) -> dict[str, FloatArray]:
    """The comparison's body measures, smoothed, NaN where unclear (arms also need wrists)."""
    base = ~unclear_mask(kp, cfg)
    wrists = np.nan_to_num(kp.kp[:, [L_WRIST, R_WRIST], 2], nan=0.0).min(axis=1) >= cfg.min_conf
    return {
        "lean": smooth(raw_lean(kp), base, cfg.fps, cfg.smooth_s),
        "arms": smooth(raw_arms(kp), base & wrists, cfg.fps, cfg.smooth_s),
        "stance": smooth(raw_stance(kp), base, cfg.fps, cfg.smooth_s),
    }

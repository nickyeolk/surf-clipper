"""Crops of a ride's rider from the 720p review copy (research R1).

The rider is the ride's own tracked person (001's track ids), so no new detection runs. Frames
are read from ``review.mp4`` (SDR, already tone-mapped, keyframe every 0.5 s) in time order:
nearby moments are reached by decoding forward, far ones by seeking.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from surfclip.riders.describe import PAD
from surfclip.rides.evidence import Obs
from surfclip.store.schemas import Ride

Image = NDArray[np.uint8]
SHARPNESS_HEIGHT = 96  # crops are resized to this height before measuring sharpness


@dataclass(frozen=True)
class Moment:
    ride_id: str
    t_s: float
    track_id: int
    box: tuple[float, float, float, float]  # source display pixels


@dataclass(frozen=True)
class Crop:
    moment: Moment
    image: Image  # padded person crop, BGR
    box_height_px: float  # in review-copy pixels
    sharpness: float


def ride_moments(ride: Ride, by_track: Mapping[int, Sequence[Obs]], n: int) -> list[Moment]:
    """``n`` observations of the ride's tracked person, evenly spread over the ride."""
    obs: list[Obs] = sorted(
        (
            o
            for t in ride.track_ids
            for o in by_track.get(t, ())
            if ride.start_s <= o.t <= ride.end_s
        ),
        key=lambda o: o.t,
    )
    if not obs:
        return []
    picks = sorted({int(i) for i in np.linspace(0, len(obs) - 1, min(n, len(obs))).round()})
    return [Moment(ride.ride_id, obs[i].t, obs[i].track_id, obs[i].box) for i in picks]


def sharpness(crop: Image) -> float:
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    scale = SHARPNESS_HEIGHT / max(gray.shape[0], 1)
    small = cv2.resize(gray, (max(1, int(gray.shape[1] * scale)), SHARPNESS_HEIGHT))
    return float(cv2.Laplacian(small, cv2.CV_64F).var())


def padded_crop(frame: Image, box: tuple[float, float, float, float], scale: float) -> Image:
    x0, y0, x1, y1 = (v * scale for v in box)
    pad = PAD * (y1 - y0)
    h, w = frame.shape[:2]
    a, b = int(max(0, x0 - pad)), int(max(0, y0 - pad))
    c, d = int(min(w, x1 + pad)), int(min(h, y1 + pad))
    return frame[b:d, a:c].copy()


def read_frames(video: Path, times: Iterable[float]) -> dict[float, Image]:
    """Frames at the given times (seconds), read in time order."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    out: dict[float, Image] = {}
    pos = -1  # index of the last frame read
    try:
        for t in sorted(set(times)):
            target = round(t * fps)
            if not (0 <= target - pos - 1 <= 2 * fps):  # far ahead or behind: seek
                cap.set(cv2.CAP_PROP_POS_FRAMES, target)
                pos = target - 1
            while pos < target - 1:
                if not cap.grab():
                    break
                pos += 1
            ok, frame = cap.read()
            pos += 1
            if ok:
                out[t] = np.asarray(frame, dtype=np.uint8)
    finally:
        cap.release()
    return out


def ride_crops(
    moments: Sequence[Moment],
    frames: Mapping[float, Image],
    scale: float,
    *,
    keep: int,
    min_height_px: float,
) -> list[Crop]:
    """The sharpest ``keep`` crops at least ``min_height_px`` tall (review-copy pixels)."""
    crops: list[Crop] = []
    for m in moments:
        frame = frames.get(m.t_s)
        if frame is None:
            continue
        height = (m.box[3] - m.box[1]) * scale
        if height < min_height_px:
            continue
        img = padded_crop(frame, m.box, scale)
        if img.size == 0:
            continue
        crops.append(Crop(m, img, height, sharpness(img)))
    crops.sort(key=lambda c: c.sharpness, reverse=True)
    return crops[:keep]

"""Small stills of a ride's rider for the UI (cached JPEGs in the session folder)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import cv2

from surfclip.riders.crops import Image, padded_crop, read_frames
from surfclip.rides.evidence import Obs
from surfclip.store.schemas import Ride, SourceInfo
from surfclip.store.session import SessionStore

STILL_HEIGHT = 160


def still_path(store: SessionStore, ride_id: str, t: float) -> Path:
    return store.path(f"stills/{ride_id}_{t:.2f}.jpg")


def save_still(store: SessionStore, ride_id: str, t: float, crop: Image) -> None:
    """Cache a crop (from the riders stage) as the ride's still at time t."""
    if crop.size == 0:
        return
    scale = STILL_HEIGHT / crop.shape[0]
    small = cv2.resize(crop, (max(1, int(crop.shape[1] * scale)), STILL_HEIGHT))
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if ok:
        path = still_path(store, ride_id, t)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(buf.tobytes())


def rider_still(
    store: SessionStore, ride: Ride, t: float, obs: Sequence[Obs]
) -> tuple[bytes, float] | None:
    """JPEG of the ride's tracked person nearest to time t (cached), and the time used."""
    from surfclip.zone.editing import display_size

    mine = [o for o in obs if o.track_id in ride.track_ids and ride.start_s <= o.t <= ride.end_s]
    if not mine:
        return None
    o = min(mine, key=lambda x: abs(x.t - t))
    cache = still_path(store, ride.ride_id, o.t)
    if cache.exists():
        return cache.read_bytes(), o.t
    frames = read_frames(store.path("review.mp4"), [o.t])
    frame = frames.get(o.t)
    if frame is None:
        return None
    width, _ = display_size(store.read_model("probe.json", SourceInfo))
    crop = padded_crop(frame, o.box, frame.shape[1] / width)
    if crop.size == 0:
        return None
    scale = STILL_HEIGHT / crop.shape[0]
    crop = cv2.resize(crop, (max(1, int(crop.shape[1] * scale)), STILL_HEIGHT))
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        return None
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(buf.tobytes())
    return buf.tobytes(), o.t

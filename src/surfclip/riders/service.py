"""Rebuild a session's riders.json from its rides, appearance and rider edits.

Called by the ``riders`` stage and by the backend after a ride or rider edit, so the file is
always reproducible from rides + appearance + edits (constitution VI/VII).
"""

from __future__ import annotations

from collections.abc import Callable

from surfclip.config import Config
from surfclip.riders.session import RIDERS_FILE, build_riders, describe_rides, ride_key
from surfclip.store.schemas import Riders, Rides
from surfclip.store.session import SessionStore

Progress = Callable[[float, str], None]


def refresh_riders(store: SessionStore, config: Config, progress: Progress | None = None) -> Riders:
    from surfclip.stages import session_observations

    rides = store.read_model("rides.json", Rides)
    detected_file = store.path("rides.detected.json")
    detected = (
        store.read_model("rides.detected.json", Rides).rides if detected_file.exists() else []
    )
    # Describe the current rides and the detected ones (the latter score grouping on detected
    # rides even after the user deleted some); each ride once.
    union = {ride_key(r): r for r in [*detected, *rides.rides]}
    if progress:
        progress(0.05, "telling riders apart: looking at each ride")
    app = describe_rides(store, list(union.values()), session_observations(store), config.riders)
    if progress:
        progress(0.9, "telling riders apart: grouping")
    riders = build_riders(
        store.session.session_id,
        rides.rides,
        app,
        config.riders,
        overlap_allowed_s=config.rides.changeover_overlap_max_s,
    )
    store.write_model(RIDERS_FILE, riders)
    return riders

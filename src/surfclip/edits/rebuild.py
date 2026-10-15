"""Rebuild rides.json from rides.detected.json + edits.json + exports.json.

Used by the rides stage and by the review UI after each edit or export, so all three always
agree (constitution VI: rides.json is reproducible from the detected rides and the edit log).
"""

from __future__ import annotations

from surfclip.edits.apply import apply_edits
from surfclip.edits.log import read_edits
from surfclip.media.export import attach_exports, read_exports
from surfclip.store.schemas import Rides
from surfclip.store.session import SessionStore

DETECTED_FILE = "rides.detected.json"
RIDES_FILE = "rides.json"


def rebuild_rides(store: SessionStore, detected: Rides | None = None) -> Rides:
    if detected is None:
        detected = store.read_model(DETECTED_FILE, Rides)
    edited = apply_edits(detected, read_edits(store))
    rides = attach_exports(edited, read_exports(store), store)
    store.write_model(RIDES_FILE, rides)
    return rides

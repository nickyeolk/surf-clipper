"""Rebuild rides.json from rides.detected.json + edits.json (+ auto_joins.json) + exports.json.

Used by the rides stage and by the review UI after each edit or export, so all three always
agree (constitution VI: rides.json is reproducible from the detected rides and the edit log).
"""

from __future__ import annotations

from surfclip.edits.apply import apply_edits, apply_joins, unjoined_pairs
from surfclip.edits.log import read_edits
from surfclip.media.export import attach_exports, read_exports
from surfclip.store.schemas import AutoJoins, Rides
from surfclip.store.session import SessionStore

DETECTED_FILE = "rides.detected.json"
RIDES_FILE = "rides.json"
AUTO_JOINS_FILE = "auto_joins.json"


def rebuild_rides(store: SessionStore, detected: Rides | None = None) -> Rides:
    if detected is None:
        detected = store.read_model(DETECTED_FILE, Rides)
    edits = read_edits(store)
    edited = apply_edits(detected, edits)
    joins_file = store.path(AUTO_JOINS_FILE)
    if joins_file.exists():  # rides split at the frame edge, joined by the riders stage
        joins = store.read_model(AUTO_JOINS_FILE, AutoJoins).joins
        edited = apply_joins(edited, joins, unjoined_pairs(edits))
    rides = attach_exports(edited, read_exports(store), store)
    store.write_model(RIDES_FILE, rides)
    return rides

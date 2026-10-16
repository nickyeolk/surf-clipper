"""Rebuild a session's riders.json from its rides, appearance and rider edits.

Called by the ``riders`` stage and by the backend after a ride or rider edit, so the file is
always reproducible from rides + appearance + edits (constitution VI/VII). Rides split at the
frame edge that are confidently one rider are joined (auto_joins.json, applied to rides.json),
then the riders are rebuilt on the joined rides.
"""

from __future__ import annotations

from collections.abc import Callable

from surfclip.config import Config
from surfclip.edits.apply import same_pair, unjoined_pairs
from surfclip.edits.log import read_edits
from surfclip.edits.rebuild import AUTO_JOINS_FILE, rebuild_rides
from surfclip.riders.edits import rider_ops
from surfclip.riders.joins import find_joins
from surfclip.riders.session import RIDERS_FILE, build_riders, describe_rides, ride_key
from surfclip.store.schemas import AutoJoins, Riders, Rides
from surfclip.store.session import SessionStore

Progress = Callable[[float, str], None]
MAX_JOIN_ROUNDS = 3  # a join can make the next one visible (a ride split three ways)


def refresh_riders(store: SessionStore, config: Config, progress: Progress | None = None) -> Riders:
    from surfclip.stages import session_observations

    obs = session_observations(store)
    detected_file = store.path("rides.detected.json")
    detected = (
        store.read_model("rides.detected.json", Rides).rides if detected_file.exists() else []
    )
    joins_file = store.path(AUTO_JOINS_FILE)
    joins = store.read_model(AUTO_JOINS_FILE, AutoJoins) if joins_file.exists() else AutoJoins()
    riders: Riders | None = None
    for _ in range(MAX_JOIN_ROUNDS):
        rides = store.read_model("rides.json", Rides)
        edits = read_edits(store)
        # Describe the current rides and the detected ones (the latter score grouping on
        # detected rides even after the user deleted some); each ride once.
        union = {ride_key(r): r for r in [*detected, *rides.rides]}
        if progress:
            progress(0.05, "telling riders apart: looking at each ride")
        app = describe_rides(store, list(union.values()), obs, config.riders)
        if progress:
            progress(0.9, "telling riders apart: grouping")
        riders = build_riders(
            store.session.session_id,
            rides.rides,
            app,
            config.riders,
            overlap_allowed_s=config.rides.changeover_overlap_max_s,
            ops=rider_ops(edits, rides.rides),
        )
        auto, suggestions = find_joins(rides.rides, riders, config.riders, unjoined_pairs(edits))
        new = [p for p in auto if not any(same_pair(p, j) for j in joins.joins)]
        riders = riders.model_copy(
            update={
                "join_suggestions": suggestions,
                "auto_joined": [(a[0], b[0]) for a, b in joins.joins],
            }
        )
        if not new:
            break
        joins = joins.model_copy(update={"joins": [*joins.joins, *new]})
        store.write_model(AUTO_JOINS_FILE, joins)
        rebuild_rides(store)  # applies the joins; then group the joined rides again
    assert riders is not None
    store.write_model(RIDERS_FILE, riders)
    return riders

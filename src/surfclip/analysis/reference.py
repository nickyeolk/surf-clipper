"""Reference clips (004 US2, research R7): an imported video of a surfer whose style the user
wants to compare with.

A reference is a session of kind ``reference``: probe, review copy, detection and tracking run
as usual, but no zone, rides or riders. The user clicks the surfer on a frame; the track under
the click is chosen, extended by tracks that continue it (the tracker can lose a surfer behind
spray), and that span becomes the clip's single ride, analysed like any ride.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
from pydantic import BaseModel

from surfclip.rides.evidence import Obs
from surfclip.store.schemas import Ride
from surfclip.store.session import SessionStore

REFERENCE_FILE = "reference.json"
REF_RIDE = "ref"
NEAR_S = 0.25  # people "at" a time: observations this close to it
CONTINUE_GAP_S = 1.0  # a track continues another if it starts within this after it ends...
CONTINUE_HEIGHTS = 1.5  # ...within this many box heights of where the other ended


class Reference(BaseModel):
    track_ids: list[int]
    start_s: float
    end_s: float
    picked_at: tuple[float, float, float]  # t, x, y (source pixels)
    picked: datetime


def people_at(obs: list[Obs], t: float) -> list[Obs]:
    """One observation per track, the nearest to t, within NEAR_S."""
    best: dict[int, Obs] = {}
    for o in obs:
        if abs(o.t - t) <= NEAR_S and (
            o.track_id not in best or abs(o.t - t) < abs(best[o.track_id].t - t)
        ):
            best[o.track_id] = o
    return list(best.values())


def pick_track(people: list[Obs], x: float, y: float) -> int | None:
    """The person under the click (smallest box containing it), else the nearest box centre."""
    if not people:
        return None
    inside = [o for o in people if o.box[0] <= x <= o.box[2] and o.box[1] <= y <= o.box[3]]
    if inside:
        return min(inside, key=lambda o: (o.box[2] - o.box[0]) * (o.box[3] - o.box[1])).track_id

    def dist(o: Obs) -> float:
        return float(np.hypot((o.box[0] + o.box[2]) / 2 - x, (o.box[1] + o.box[3]) / 2 - y))

    return min(people, key=dist).track_id


def _centre(o: Obs) -> tuple[float, float]:
    return ((o.box[0] + o.box[2]) / 2, (o.box[1] + o.box[3]) / 2)


def continuation(obs: list[Obs], chosen: int) -> list[int]:
    """The chosen track plus tracks that continue it before and after (greedy, one at a time)."""
    tracks: dict[int, list[Obs]] = {}
    for o in sorted(obs, key=lambda o: o.t):
        tracks.setdefault(o.track_id, []).append(o)
    if chosen not in tracks:
        return []
    chain = [chosen]
    used = {chosen}
    while True:  # forwards
        last = tracks[chain[-1]][-1]
        nxt = _closest(tracks, used, last, after=True)
        if nxt is None:
            break
        chain.append(nxt)
        used.add(nxt)
    while True:  # backwards
        first = tracks[chain[0]][0]
        prev = _closest(tracks, used, first, after=False)
        if prev is None:
            break
        chain.insert(0, prev)
        used.add(prev)
    return chain


def _closest(tracks: dict[int, list[Obs]], used: set[int], end: Obs, *, after: bool) -> int | None:
    h = max(end.box[3] - end.box[1], 1.0)
    ex, ey = _centre(end)
    best: tuple[float, int] | None = None
    for tid, os in tracks.items():
        if tid in used:
            continue
        o = os[0] if after else os[-1]
        gap = (o.t - end.t) if after else (end.t - o.t)
        if not 0 <= gap <= CONTINUE_GAP_S:
            continue
        ox, oy = _centre(o)
        d = float(np.hypot(ox - ex, oy - ey)) / h
        if d <= CONTINUE_HEIGHTS and (best is None or d < best[0]):
            best = (d, tid)
    return best[1] if best else None


def choose_surfer(store: SessionStore, obs: list[Obs], t: float, x: float, y: float) -> Reference:
    tid = pick_track(people_at(obs, t), x, y)
    if tid is None:
        raise ValueError("nobody is visible at that moment: pick another frame")
    chain = continuation(obs, tid)
    times = [o.t for o in obs if o.track_id in chain]
    ref = Reference(
        track_ids=chain, start_s=min(times), end_s=max(times), picked_at=(t, x, y),
        picked=datetime.now(UTC),
    )  # fmt: skip
    store.write_model(REFERENCE_FILE, ref)
    return ref


def read_reference(store: SessionStore) -> Reference | None:
    path = store.path(REFERENCE_FILE)
    return store.read_model(REFERENCE_FILE, Reference) if path.exists() else None


def reference_ride(store: SessionStore) -> Ride | None:
    ref = read_reference(store)
    if ref is None:
        return None
    return Ride(
        ride_id=REF_RIDE, start_s=ref.start_s, end_s=ref.end_s, confidence=1.0,
        start_frame=0, end_frame=0, clip_start_s=ref.start_s, clip_end_s=ref.end_s,
        epochs=[0], track_ids=ref.track_ids,
    )  # fmt: skip

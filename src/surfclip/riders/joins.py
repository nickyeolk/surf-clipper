"""Join rides split at the frame edge (FR-011, research R7).

001 splits a ride in two when the rider leaves the frame and comes back (portrait or tight
framing). Once riders are known, two consecutive rides of one rider separated by a short gap,
with the rider at the frame edge, are one ride: joined automatically when both are confidently
that rider, otherwise offered as a one-click suggestion.
"""

from __future__ import annotations

from collections.abc import Sequence

from surfclip.config import RidersConfig
from surfclip.edits.apply import same_pair
from surfclip.store.schemas import JoinSuggestion, Ride, RideRef, Riders


def _ref(r: Ride) -> RideRef:
    return (r.ride_id, round(r.start_s, 3), round(r.end_s, 3))


def find_joins(
    rides: Sequence[Ride],
    riders: Riders,
    cfg: RidersConfig,
    unjoined: Sequence[tuple[RideRef, RideRef]] = (),
) -> tuple[list[tuple[RideRef, RideRef]], list[JoinSuggestion]]:
    """(automatic joins, suggestions) among the current rides."""
    card = {a.ride_id: a.rider_id for a in riders.assignments}
    sure = {
        a.ride_id: a.confirmed or a.confidence >= cfg.join_confidence for a in riders.assignments
    }
    conf = {a.ride_id: a.confidence for a in riders.assignments}
    ignored = {g.rider_id for g in riders.riders if g.ignored}
    ordered = sorted(rides, key=lambda r: r.start_s)
    auto: list[tuple[RideRef, RideRef]] = []
    suggest: list[JoinSuggestion] = []
    for i, a in enumerate(ordered):
        rider = card.get(a.ride_id)
        if rider is None or rider in ignored or not a.flags.truncated:
            continue
        nxt = next((b for b in ordered[i + 1 :] if b.start_s >= a.end_s), None)
        if nxt is None:
            continue
        gap = nxt.start_s - a.end_s
        between = [r for r in ordered if a.end_s < r.start_s < nxt.start_s]
        if card.get(nxt.ride_id) != rider or gap > cfg.join_gap_s or between:
            continue
        if not (nxt.start_kind == "off_frame" or nxt.flags.truncated):
            continue
        pair = (_ref(a), _ref(nxt))
        if any(same_pair(pair, u) for u in unjoined):
            continue
        if sure.get(a.ride_id) and sure.get(nxt.ride_id):
            auto.append(pair)
        else:
            suggest.append(
                JoinSuggestion(
                    first=a.ride_id,
                    second=nxt.ride_id,
                    gap_s=round(gap, 2),
                    confidence=round(min(conf.get(a.ride_id, 0.0), conf.get(nxt.ride_id, 0.0)), 3),
                )
            )
    return auto, suggest

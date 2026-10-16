"""T015: rider edits applied to the cards (name, same as, mixed, ignore, move, undo, re-attach)."""

from collections.abc import Mapping
from datetime import UTC, datetime

import numpy as np

from surfclip.config import load_config
from surfclip.riders.describe import RideDescriptor
from surfclip.riders.edits import rider_ops
from surfclip.riders.session import Appearance, Described, build_riders, ride_key
from surfclip.store.schemas import EditOp, Edits, EditTarget, Ride, Riders, UserEdit

CFG = load_config().riders.model_copy(update={"cluster_threshold": 0.05})
DIRS = {"a": [1.0, 0.0, 0.0], "b": [0.0, 1.0, 0.0], "c": [0.0, 0.0, 1.0]}
# Rides 0..8 every 100 s; rider a rides 0, 3, 6; b rides 1, 4, 7; c rides 2, 5, 8.
WHO = {k: "abc"[k % 3] for k in range(9)}
Edit = tuple[EditOp, dict[str, object]]


def ride(k: int, shift: float = 0.0, rid: str | None = None) -> Ride:
    s = 100.0 * k + shift
    return Ride(ride_id=rid or f"r{k}", start_s=s, end_s=s + 30, confidence=0.9,
                start_frame=0, end_frame=0, clip_start_s=s, clip_end_s=s + 30, epochs=[0],
                track_ids=[k])  # fmt: skip


def appearance(rides: list[Ride], who: Mapping[int, str] = WHO) -> Appearance:
    rng = np.random.default_rng(1)
    out: dict[str, Described] = {}
    for k, r in enumerate(rides):
        e = np.array(DIRS[who[k]]) + rng.normal(0, 0.02, 3)
        desc = RideDescriptor(r.ride_id, np.zeros(1), 8, False, 100.0 + k)
        out[ride_key(r)] = Described(desc, r.start_s, e)
    return Appearance(np.ones(3), out, "embedding")


def log(*edits: Edit) -> Edits:
    return Edits(edits=[UserEdit(edit_id=i, at=datetime(2026, 10, 16, tzinfo=UTC), op=op,
                                 target=EditTarget(), payload=p)
                        for i, (op, p) in enumerate(edits, start=1)])  # fmt: skip


def spans(*ks: int) -> dict[str, object]:
    return {f"r{k}": [100.0 * k, 100.0 * k + 30] for k in ks}


def ref(k: int) -> list[object]:
    return [f"r{k}", 100.0 * k, 100.0 * k + 30]


def card(riders: Riders, ride_id: str) -> tuple[str | None, list[str], bool]:
    g = next(g for g in riders.riders if ride_id in g.ride_ids)
    return g.name, sorted(g.ride_ids), g.ignored


def build(rides: list[Ride], edits: Edits) -> Riders:
    return build_riders("s", rides, appearance(rides), CFG, overlap_allowed_s=2.0,
                        ops=rider_ops(edits, rides))  # fmt: skip


RIDES = [ride(k) for k in range(9)]
NAME_A: Edit = ("rider_name", {"name": "me", "rides": spans(0, 3, 6), "examples": spans(0, 3)})
NAME_B: Edit = ("rider_name", {"name": "pat", "rides": spans(1, 4, 7), "examples": spans(1)})
SAME: Edit = ("rider_same_as", {"rides": spans(0, 3, 6), "other": spans(1, 4, 7)})
AB = ["r0", "r1", "r3", "r4", "r6", "r7"]


def test_no_edits_three_riders() -> None:
    riders = build(RIDES, log())
    assert len(riders.riders) == 3 and all(g.name is None for g in riders.riders)


def test_name_confirms_only_the_main_example() -> None:
    riders = build(RIDES, log(NAME_A))
    assert card(riders, "r3") == ("me", ["r0", "r3", "r6"], False)
    assert {a.ride_id for a in riders.assignments if a.confirmed} == {"r0"}


def test_rename_and_same_name_twice_is_one_person() -> None:
    rename: Edit = ("rider_name", {"name": "lik", "rides": spans(0, 3, 6), "examples": spans(3)})
    assert card(build(RIDES, log(NAME_A, rename)), "r0")[0] == "lik"
    twice: Edit = ("rider_name", {"name": "me", "rides": spans(1, 4, 7), "examples": spans(1)})
    assert card(build(RIDES, log(NAME_A, twice)), "r1")[1] == AB


def test_same_as_mixed_and_ignore() -> None:
    assert card(build(RIDES, log(SAME)), "r0")[1] == AB
    mixed: Edit = ("rider_mixed", {"rides": spans(0, 1, 3, 4, 6, 7)})
    riders = build(RIDES, log(SAME, mixed))
    assert card(riders, "r0")[1] == ["r0", "r3", "r6"]
    assert card(riders, "r1")[1] == ["r1", "r4", "r7"]
    ignore: Edit = ("rider_ignore", {"rides": spans(2, 5, 8), "ignore": True})
    assert card(build(RIDES, log(ignore)), "r5")[2]


def test_moving_a_ride_changes_nothing_else() -> None:
    """2026-10-16: moving rides out of a card let other riders' rides flow into it."""
    before = {g.rider_id: sorted(g.ride_ids) for g in build(RIDES, log()).riders}
    after = build(RIDES, log(("ride_rider", {"ride": ref(6), "same_as_ride": ref(1)})))
    assert card(after, "r6")[1] == ["r1", "r4", "r6", "r7"]
    changed = {g.rider_id for g in after.riders if sorted(g.ride_ids) != before[g.rider_id]}
    assert len(changed) == 2  # only the card the ride left and the one it joined


def test_move_to_a_name_and_out_of_a_name() -> None:
    riders = build(RIDES, log(("ride_rider", {"ride": ref(8), "name": "pat"})))
    assert card(riders, "r8") == ("pat", ["r8"], False)
    riders = build(RIDES, log(NAME_A, ("ride_rider", {"ride": ref(6), "not_name": "me"})))
    assert "r6" not in card(riders, "r0")[1]


def test_moving_a_shown_example_keeps_both_named_riders() -> None:
    """20261012: one of "me"'s stills was pat's ride; moving it must not merge the two."""
    move: Edit = ("ride_rider", {"ride": ref(3), "same_as_ride": ref(1), "away_from": ref(0)})
    riders = build(RIDES, log(NAME_A, NAME_B, move))
    assert card(riders, "r1") == ("pat", ["r1", "r3", "r4", "r7"], False)
    assert card(riders, "r0") == ("me", ["r0", "r6"], False)


def test_same_as_between_named_riders_keeps_the_first_name() -> None:
    riders = build(RIDES, log(NAME_A, NAME_B, SAME))
    assert card(riders, "r4")[0] == "me" and all(g.name != "pat" for g in riders.riders)


def test_undo_and_reattach_after_rerun() -> None:
    assert card(build(RIDES, log(NAME_A, ("undo", {"edit_id": 1}))), "r0")[0] is None
    rerun = [ride(k, 0.4, rid=f"x{k}") for k in range(9)]  # re-detected: shifted, renamed
    assert card(build(rerun, log(NAME_A)), "x3")[0] == "me"

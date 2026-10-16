"""T015: rider edits as grouping rules (name, same as, mixed, ignore, undo, re-attach)."""

from collections.abc import Mapping
from datetime import UTC, datetime

import numpy as np

from surfclip.config import load_config
from surfclip.riders.describe import RideDescriptor
from surfclip.riders.edits import rider_rules
from surfclip.riders.session import Appearance, Described, build_riders, ride_key
from surfclip.store.schemas import EditOp, Edits, EditTarget, Ride, Riders, UserEdit

CFG = load_config().riders.model_copy(update={"cluster_threshold": 0.05})
DIRS = {"a": [1.0, 0.0, 0.0], "b": [0.0, 1.0, 0.0], "c": [0.0, 0.0, 1.0]}
# Rides 0..8 every 100 s; rider a rides 0, 3, 6; b rides 1, 4, 7; c rides 2, 5, 8.
WHO = {k: "abc"[k % 3] for k in range(9)}


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
        out[ride_key(r)] = Described(
            RideDescriptor(r.ride_id, np.zeros(1), 8, False, 100.0 + k), r.start_s, e
        )
    return Appearance(np.ones(3), out, "embedding")


def log(*edits: tuple[EditOp, dict[str, object]]) -> Edits:
    return Edits(edits=[UserEdit(edit_id=i, at=datetime(2026, 10, 16, tzinfo=UTC), op=op,
                                 target=EditTarget(), payload=p)
                        for i, (op, p) in enumerate(edits, start=1)])  # fmt: skip


def more(base: Edits, *extra: tuple[EditOp, dict[str, object]]) -> Edits:
    n = len(base.edits)
    return Edits(
        edits=[
            *base.edits,
            *(
                UserEdit(edit_id=n + i, at=datetime(2026, 10, 16, tzinfo=UTC), op=op,
                         target=EditTarget(), payload=p)
                for i, (op, p) in enumerate(extra, start=1)
            ),
        ]
    )  # fmt: skip


def spans(*ks: int) -> dict[str, list[float]]:
    return {f"r{k}": [100.0 * k, 100.0 * k + 30] for k in ks}


def group(riders: Riders, ride_id: str) -> tuple[str | None, list[str], bool]:
    g = next(g for g in riders.riders if ride_id in g.ride_ids)
    return g.name, sorted(g.ride_ids), g.ignored


def build(rides: list[Ride], edits: Edits, app: Appearance | None = None) -> Riders:
    return build_riders("s", rides, app or appearance(rides), CFG, overlap_allowed_s=2.0,
                        rules=rider_rules(edits, rides))  # fmt: skip


RIDES = [ride(k) for k in range(9)]


def test_no_edits_three_riders() -> None:
    riders = build(RIDES, log())
    assert len(riders.riders) == 3 and all(g.name is None for g in riders.riders)


def test_name_confirms_examples_and_rename() -> None:
    edits = log(("rider_name", {"name": "me", "rides": spans(0, 3, 6), "examples": spans(0)}))
    riders = build(RIDES, edits)
    assert group(riders, "r3") == ("me", ["r0", "r3", "r6"], False)
    a = next(x for x in riders.assignments if x.ride_id == "r0")
    assert a.confirmed and a.confidence == 1.0
    rename = {"name": "lik", "rides": spans(0, 3, 6), "examples": spans(3)}
    renamed = more(edits, ("rider_name", rename))
    assert group(build(RIDES, renamed), "r0")[0] == "lik"


def test_same_as_mixed_and_ignore() -> None:
    same = log(("rider_same_as", {"rides": spans(0, 3, 6), "other": spans(1, 4, 7)}))
    assert group(build(RIDES, same), "r0")[1] == ["r0", "r1", "r3", "r4", "r6", "r7"]
    mixed = more(same,
                ("rider_mixed", {"rides": spans(0, 1, 3, 4, 6, 7)}))  # fmt: skip
    assert group(build(RIDES, mixed), "r0")[1] == ["r0", "r3", "r6"]
    ignore = log(("rider_ignore", {"rides": spans(2, 5, 8), "ignore": True}))
    assert group(build(RIDES, ignore), "r5")[2]


def test_ride_answers() -> None:
    # r6 is truly rider a; a "not me" answer moves it out of "me", "same as" joins it back.
    edits = log(
        ("rider_name", {"name": "me", "rides": spans(0, 3, 6), "examples": spans(0)}),
        ("ride_rider", {"ride": ["r6", 600.0, 630.0], "not_name": "me"}),
    )
    assert "r6" not in group(build(RIDES, edits), "r0")[1]
    back = more(edits,
               ("ride_rider", {"ride": ["r6", 600.0, 630.0], "name": "me"}))  # fmt: skip
    assert "r6" in group(build(RIDES, back), "r0")[1]


def test_undo_and_reattach_after_rerun() -> None:
    edits = log(
        ("rider_name", {"name": "me", "rides": spans(0, 3, 6), "examples": spans(0)}),
        ("undo", {"edit_id": 1}),
    )
    assert group(build(RIDES, edits), "r0")[0] is None
    # A re-run shifts every ride by 0.4 s and renames it: the name still applies.
    rerun = [ride(k, 0.4, rid=f"x{k}") for k in range(9)]
    named = log(("rider_name", {"name": "me", "rides": spans(0, 3, 6), "examples": spans(0)}))
    assert group(build(rerun, named), "x3")[0] == "me"


def test_move_one_ride_to_another_rider() -> None:
    # r6 (rider a) moved to rider b's card: joins b's example, apart from a's example.
    move = log(("ride_rider", {"ride": ["r6", 600.0, 630.0], "same_as_ride": ["r1", 100.0, 130.0],
                               "away_from": ["r0", 0.0, 30.0]}))  # fmt: skip
    riders = build(RIDES, move)
    assert "r6" in group(riders, "r1")[1] and "r6" not in group(riders, "r0")[1]


def test_mixed_after_same_as_splits_again() -> None:
    same = log(("rider_same_as", {"rides": spans(0, 3, 6), "other": spans(1, 4, 7)}))
    mixed = more(same, ("rider_mixed", {"rides": spans(0, 1, 3, 4, 6, 7)}))
    riders = build(RIDES, mixed)
    assert group(riders, "r0")[1] == ["r0", "r3", "r6"]
    assert group(riders, "r1")[1] == ["r1", "r4", "r7"]


def test_moving_a_locked_example_does_not_merge_two_named_riders() -> None:
    """20261012: one of "me"'s stills was someone else; moving it to marcus's card must not drag
    marcus into "me"."""
    edits = log(
        ("rider_name", {"name": "me", "rides": spans(0, 3, 6), "examples": spans(0, 3)}),
        ("rider_name", {"name": "marcus", "rides": spans(1, 4, 7), "examples": spans(1)}),
        ("ride_rider", {"ride": ["r3", 300.0, 330.0], "same_as_ride": ["r1", 100.0, 130.0],
                        "away_from": ["r0", 0.0, 30.0]}),
    )  # fmt: skip
    riders = build(RIDES, edits)
    assert group(riders, "r1") == ("marcus", ["r1", "r3", "r4", "r7"], False)
    assert group(riders, "r0") == ("me", ["r0", "r6"], False)


def test_same_as_between_named_riders_keeps_one_name() -> None:
    edits = log(
        ("rider_name", {"name": "me", "rides": spans(0, 3, 6), "examples": spans(0)}),
        ("rider_name", {"name": "lik", "rides": spans(1, 4, 7), "examples": spans(1)}),
        ("rider_same_as", {"rides": spans(0, 3, 6), "other": spans(1, 4, 7)}),
    )
    riders = build(RIDES, edits)
    assert group(riders, "r4")[0] == "me" and "r4" in group(riders, "r0")[1]
    assert all(g.name != "lik" for g in riders.riders)


def test_moving_the_pivot_of_a_merge_keeps_the_rest_together() -> None:
    edits = log(
        ("rider_same_as", {"rides": spans(0, 3, 6), "other": spans(1, 4, 7)}),
        ("ride_rider", {"ride": ["r0", 0.0, 30.0], "same_as_ride": ["r2", 200.0, 230.0],
                        "away_from": ["r3", 300.0, 330.0]}),
    )  # fmt: skip
    riders = build(RIDES, edits)
    assert group(riders, "r3")[1] == ["r1", "r3", "r4", "r6", "r7"]
    assert "r0" in group(riders, "r2")[1]

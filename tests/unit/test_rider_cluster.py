"""T004: grouping rides into riders under time-overlap and user constraints."""

import numpy as np

from surfclip.riders.cluster import Constraints, group_rides, split_two


def euclid(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def session(n_per: int = 4) -> tuple[dict[str, np.ndarray], dict[str, tuple[float, float]]]:
    """Three riders (well-separated descriptors) taking turns: rides 30 s long, 40 s apart."""
    rng = np.random.default_rng(0)
    centres = [np.array([0.0, 0.0]), np.array([5.0, 0.0]), np.array([0.0, 5.0])]
    desc: dict[str, np.ndarray] = {}
    spans: dict[str, tuple[float, float]] = {}
    for k in range(3 * n_per):
        rid = f"r{k:02d}"
        desc[rid] = centres[k % 3] + rng.normal(0, 0.2, 2)
        spans[rid] = (40.0 * k, 40.0 * k + 30.0)
    return desc, spans


def test_three_riders_are_recovered() -> None:
    desc, spans = session()
    groups = group_rides(desc, spans, euclid, threshold=1.5, overlap_allowed_s=2.0)
    assert len(groups) == 3
    for g in groups:
        assert len({int(r[1:]) % 3 for r in g}) == 1  # one rider per group


def test_rides_overlapping_in_time_are_never_one_rider() -> None:
    desc = {"a": np.zeros(2), "b": np.zeros(2) + 0.01}
    spans = {"a": (0.0, 30.0), "b": (20.0, 50.0)}  # 10 s overlap: two people on the wave
    groups = group_rides(desc, spans, euclid, threshold=1.0, overlap_allowed_s=2.0)
    assert len(groups) == 2


def test_changeover_overlap_is_allowed() -> None:
    desc = {"a": np.zeros(2), "b": np.zeros(2) + 0.01}
    spans = {"a": (0.0, 30.0), "b": (29.0, 50.0)}  # 1 s overlap: a changeover
    assert len(group_rides(desc, spans, euclid, threshold=1.0, overlap_allowed_s=2.0)) == 1


def test_groups_are_ordered_by_size_then_time() -> None:
    desc = {"a": np.zeros(2), "b": np.zeros(2), "c": np.ones(2) * 9, "d": np.ones(2) * 9.1,
            "e": np.ones(2) * 9.2, "f": np.array([20.0, 0.0])}  # fmt: skip
    spans = {k: (100.0 * i, 100.0 * i + 30) for i, k in enumerate("abcdef")}
    groups = group_rides(desc, spans, euclid, threshold=1.0, overlap_allowed_s=2.0)
    assert groups == [["c", "d", "e"], ["a", "b"], ["f"]]


def test_user_constraints() -> None:
    desc, spans = session()
    # Same rider joins two far-apart rides; different riders splits two close ones.
    must = Constraints(must=[("r00", "r01")])
    groups = group_rides(
        desc, spans, euclid, threshold=1.5, overlap_allowed_s=2.0, constraints=must
    )
    assert any({"r00", "r01"} <= set(g) for g in groups)
    cannot = Constraints(cannot=[("r00", "r03")])
    groups = group_rides(
        desc, spans, euclid, threshold=1.5, overlap_allowed_s=2.0, constraints=cannot
    )
    assert not any({"r00", "r03"} <= set(g) for g in groups)
    fixed = Constraints(fixed={"r00": "me", "r03": "pat"})
    groups = group_rides(
        desc, spans, euclid, threshold=1.5, overlap_allowed_s=2.0, constraints=fixed
    )
    assert not any({"r00", "r03"} <= set(g) for g in groups)


def test_split_in_two() -> None:
    desc, spans = session()
    two = {k: v for k, v in desc.items() if int(k[1:]) % 3 in (0, 1)}
    groups = group_rides(
        two, {k: spans[k] for k in two}, euclid, threshold=float("inf"),
        overlap_allowed_s=2.0, stop_at=2,
    )  # fmt: skip
    assert len(groups) == 2
    assert all(len({int(r[1:]) % 3 for r in g}) == 1 for g in groups)


def test_split_two_always_splits() -> None:
    desc, _ = session()
    two = [k for k in desc if int(k[1:]) % 3 in (0, 1)]
    first, second = split_two(two, desc, euclid)
    assert first and second
    assert {int(r[1:]) % 3 for r in first} != {int(r[1:]) % 3 for r in second}
    assert all(len({int(r[1:]) % 3 for r in h}) == 1 for h in (first, second))

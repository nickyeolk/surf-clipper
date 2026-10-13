"""Stitching track fragments of one person (tracks break every few seconds at 5 fps)."""

from surfclip.rides.evidence import Obs
from surfclip.rides.stitch import stitch
from tests.unit.ride_synth import Seg, ride_segment, rides_cfg, track


def _ids(chains: dict[int, list[Obs]]) -> list[list[int]]:
    return sorted(sorted({o.track_id for o in obs}) for obs in chains.values())


def test_fragments_with_short_gaps_become_one_chain() -> None:
    a = track(1, 0.0, ride_segment(3.0, 0.1, 0.25))
    b = track(2, a[-1].t + 0.6, ride_segment(3.0, 0.27, 0.42))
    c = track(3, b[-1].t + 0.4, ride_segment(3.0, 0.44, 0.6))
    chains, members = stitch([a, b, c], rides_cfg())
    assert len(chains) == 1
    (chain_id,) = chains
    assert members[chain_id] == [1, 2, 3]
    assert {o.track_id for o in chains[chain_id]} == {chain_id}


def test_long_gap_is_not_stitched() -> None:
    a = track(1, 0.0, ride_segment(3.0, 0.1, 0.25))
    b = track(2, a[-1].t + 3.0, ride_segment(3.0, 0.27, 0.42))
    chains, _ = stitch([a, b], rides_cfg())
    assert len(chains) == 2


def test_far_away_fragment_is_not_stitched() -> None:
    a = track(1, 0.0, ride_segment(3.0, 0.1, 0.25))
    b = track(2, a[-1].t + 0.4, ride_segment(3.0, 0.9, 0.95, v=0.9))
    chains, _ = stitch([a, b], rides_cfg())
    assert len(chains) == 2


def test_simultaneous_people_are_not_stitched() -> None:
    a = track(1, 0.0, ride_segment(6.0, 0.1, 0.4))
    b = track(2, 2.0, ride_segment(6.0, 0.12, 0.42, v=0.45))
    chains, _ = stitch([a, b], rides_cfg())
    assert len(chains) == 2


def test_each_fragment_has_at_most_one_successor() -> None:
    a = track(1, 0.0, ride_segment(3.0, 0.1, 0.25))
    b = track(2, a[-1].t + 0.4, ride_segment(3.0, 0.26, 0.4))
    c = track(3, a[-1].t + 0.6, Seg(3.0, 0.27, 0.3, board=False))
    chains, members = stitch([a, b, c], rides_cfg())
    assert len(chains) == 2
    assert [1, 2] in members.values()

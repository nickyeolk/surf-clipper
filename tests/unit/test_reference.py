"""004 T018: reference clips choose the clicked surfer and follow them across track breaks."""

from surfclip.analysis.reference import continuation, people_at, pick_track
from surfclip.rides.evidence import Obs


def _o(track: int, t: float, box: tuple[float, float, float, float]) -> Obs:
    return Obs(t=t, frame=int(t * 5), track_id=track, box=box, feet=((box[0] + box[2]) / 2, box[3]),
               score=0.9, board=True, stance="standing", edge=None)  # type: ignore[arg-type]  # fmt: skip


def test_click_picks_the_person_under_it_else_the_nearest() -> None:
    big = _o(1, 1.0, (0, 0, 400, 400))
    small = _o(2, 1.0, (100, 100, 200, 300))  # inside the big box
    far = _o(3, 1.0, (600, 100, 700, 300))
    people = [big, small, far]
    assert pick_track(people, 150, 200) == 2  # smallest box containing the click
    assert pick_track(people, 50, 50) == 1
    assert pick_track(people, 560, 200) == 3  # outside every box: nearest centre
    assert pick_track([], 0, 0) is None


def test_people_at_one_per_track_nearest_in_time() -> None:
    obs = [_o(1, 0.9, (0, 0, 1, 1)), _o(1, 1.05, (5, 5, 6, 6)), _o(2, 2.0, (0, 0, 1, 1))]
    (p,) = people_at(obs, 1.0)
    assert p.box == (5, 5, 6, 6)


def test_continuation_joins_tracks_that_carry_on() -> None:
    a = [_o(1, t, (100 + 10 * t, 100, 150 + 10 * t, 200)) for t in (0.0, 0.2, 0.4)]
    b = [_o(2, t, (110 + 10 * t, 100, 160 + 10 * t, 200)) for t in (1.0, 1.2)]  # 0.6 s later, close
    c = [_o(3, t, (900, 100, 950, 200)) for t in (1.0, 1.2)]  # someone else, far away
    d = [_o(4, t, (130, 100, 180, 200)) for t in (5.0,)]  # too late
    assert continuation(a + b + c + d, 1) == [1, 2]
    assert continuation(a + b + c + d, 2) == [1, 2]
    assert continuation(a, 9) == []

import numpy as np

from surfclip.config import load_config
from surfclip.detect.tiling import merge, tile_windows, touches_inner_border
from surfclip.track.people import feet_point, frame_edge, match_boards, stance

CFG = load_config().track


def test_tiles_cover_frame_with_overlap() -> None:
    wins = tile_windows(1280, 720, 0.2)
    assert len(wins) == 4
    assert wins[0] == (0, 0, 768, 432)
    assert wins[-1] == (512, 288, 1280, 720)


def test_portrait_tiles() -> None:
    wins = tile_windows(540, 720, 0.2)
    assert {w[2] for w in wins} == {324, 540} and {w[3] for w in wins} == {432, 720}


def test_inner_border_box_is_flagged_outer_border_is_not() -> None:
    win = (0, 0, 768, 432)
    assert touches_inner_border(np.array([700.0, 100, 767, 300]), win, 1280, 720)
    assert not touches_inner_border(np.array([0.0, 100, 50, 300]), win, 1280, 720)


def test_merge_keeps_best_of_duplicates_per_class() -> None:
    boxes = np.array([[0, 0, 10, 20], [0.5, 0, 10.5, 20], [0, 0, 10, 20]], dtype=float)
    scores = np.array([0.6, 0.9, 0.7])
    classes = np.array([0, 0, 1])
    assert merge(boxes, scores, classes, 0.5).tolist() == [1, 2]


def test_frame_edge() -> None:
    assert frame_edge((0, 100, 50, 300), 1280, 720, CFG) == "left"
    assert frame_edge((1200, 100, 1280, 300), 1280, 720, CFG) == "right"
    assert frame_edge((600, 500, 700, 720), 1280, 720, CFG) == "bottom"
    assert frame_edge((600, 100, 700, 300), 1280, 720, CFG) == "none"


def test_stance_from_aspect() -> None:
    assert stance((0, 0, 100, 250), CFG) == "standing"
    assert stance((0, 0, 100, 120), CFG) == "crouched"
    assert stance((0, 0, 100, 60), CFG) == "sitting"


def test_board_under_feet_is_matched_once() -> None:
    rider = (100.0, 100.0, 150.0, 300.0)  # feet at (125, 300), height 200 -> reach 70
    other = (400.0, 100.0, 450.0, 300.0)
    board = (90.0, 290.0, 170.0, 320.0)
    far_board = (700.0, 290.0, 780.0, 320.0)
    assert match_boards([rider, other], [board, far_board], CFG) == [0, None]


def test_board_held_overhead_is_not_under_feet() -> None:
    person = (100.0, 100.0, 150.0, 300.0)
    held = (90.0, 60.0, 170.0, 110.0)
    assert match_boards([person], [held], CFG) == [None]


def test_feet_from_board_when_bottom_is_cut_off() -> None:
    box = (600.0, 400.0, 700.0, 720.0)
    board = (580.0, 690.0, 720.0, 720.0)
    assert feet_point(box, board, "bottom") == (650.0, 705.0)
    assert feet_point(box, None, "none") == (650.0, 720.0)

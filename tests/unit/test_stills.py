"""003 T015: still frame snapping and names."""

import pytest

from surfclip.media.stills import StillError, delete_still, snap


def test_snap_to_the_frame_grid() -> None:
    assert snap(10.0, 30.0) == (300, 10.0)
    assert snap(10.016, 30.0) == (300, 10.0)
    assert snap(10.02, 30.0) == (301, 301 / 30)
    assert snap(-0.01, 30.0) == (0, 0.0)
    frame, t = snap(100.0, 25.68)
    assert frame == 2568 and t == pytest.approx(100.0)


def test_delete_rejects_paths() -> None:
    with pytest.raises(StillError):
        delete_still(None, "../rides.json")  # type: ignore[arg-type]

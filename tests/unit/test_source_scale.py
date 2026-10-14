"""Zones are in source display pixels; detections are scaled up from the analysis frame."""

from typing import Any

import pytest

from surfclip.rides.evidence import to_source_pixels
from surfclip.stages import source_scale
from surfclip.store.frames import FrameMeta
from surfclip.store.schemas import SourceInfo
from tests.unit.ride_synth import Seg, track


def _info(**kw: Any) -> SourceInfo:
    base: dict[str, Any] = {
        "path": "x",
        "container": "mp4",
        "codec": "h264",
        "width": 1280,
        "height": 720,
        "duration_s": 60,
        "avg_fps": 30,
        "is_vfr": False,
        "bit_depth": 8,
        "pix_fmt": "yuv420p",
        "hdr_format": "none",
    }
    return SourceInfo.model_validate(base | kw)


@pytest.mark.parametrize(
    ("info", "meta", "expected"),
    [
        (_info(), FrameMeta(1280, 720, 5), (1.0, 1.0)),
        (_info(width=960, height=1280), FrameMeta(540, 720, 5), (960 / 540, 1280 / 720)),
        (_info(width=1920, height=1080, rotation=180), FrameMeta(1280, 720, 5), (1.5, 1.5)),
        (
            _info(width=1920, height=1080, rotation=90),
            FrameMeta(406, 720, 5),
            (1080 / 406, 1920 / 720),
        ),
    ],
    ids=["archive-720p", "portrait", "hdr-1080p-upside-down", "rotated-portrait"],
)
def test_source_scale(info: SourceInfo, meta: FrameMeta, expected: tuple[float, float]) -> None:
    assert source_scale(info, meta) == pytest.approx(expected)


def test_observations_scale_boxes_and_feet() -> None:
    (o,) = track(1, 0.0, Seg(0.2, 0.5, 0.5))
    (s,) = to_source_pixels([o], 1.5, 2.0)
    assert s.feet == (o.feet[0] * 1.5, o.feet[1] * 2.0)
    assert s.box_height == pytest.approx(o.box_height * 2.0)
    assert to_source_pixels([o], 1.0, 1.0) == [o]

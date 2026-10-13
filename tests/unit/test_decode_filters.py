from typing import Any

from surfclip.media.decode import build_filter, output_size
from surfclip.store.schemas import SourceInfo


def _info(**kw: Any) -> SourceInfo:
    base: dict[str, Any] = {
        "path": "x.mp4",
        "container": "mp4",
        "codec": "hevc",
        "width": 3840,
        "height": 2160,
        "duration_s": 60.0,
        "avg_fps": 30.0,
        "is_vfr": False,
        "bit_depth": 10,
        "pix_fmt": "yuv420p10le",
        "hdr_format": "none",
    }
    return SourceInfo.model_validate(base | kw)


def test_4k_is_downscaled_to_720_keeping_aspect() -> None:
    assert output_size(_info(), 720) == (1280, 720)


def test_720p_is_kept() -> None:
    assert output_size(_info(width=1280, height=720), 720) == (1280, 720)


def test_portrait_rotation_swaps_dimensions() -> None:
    assert output_size(_info(rotation=90), 720) == (406, 720)


def test_sdr_filter_has_no_tonemap() -> None:
    vf = build_filter(_info(), fps=5, max_height=720, tonemap="hable")
    assert vf.startswith("select=") and "tonemap" not in vf and vf.endswith("format=bgr24,showinfo")


def test_hdr_filter_tonemaps_before_scaling() -> None:
    vf = build_filter(_info(hdr_format="hlg"), fps=5, max_height=720, tonemap="hable")
    assert vf.index("tonemap=hable") < vf.index("scale=1280:720")

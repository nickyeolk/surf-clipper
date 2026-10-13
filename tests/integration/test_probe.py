"""Probe the real evaluation sessions (read-only). Set SURFCLIP_SAMPLES to their folder."""

import os
from pathlib import Path

import pytest

from surfclip.media.decode import output_size
from surfclip.media.probe import probe

SAMPLES = Path(os.environ.get("SURFCLIP_SAMPLES", "/mnt/c/Users/likkhian/OneDrive/Media/trifecta"))

pytestmark = pytest.mark.integration


def _sample(name: str) -> Path:
    path = SAMPLES / name
    if not path.exists():
        pytest.skip(f"{path} not available")
    return path


@pytest.mark.parametrize("name", ["20240924.MP4", "20241004.MP4"])
def test_archive_sessions_are_720p30_sdr(name: str) -> None:
    info = probe(_sample(name))
    assert (info.codec, info.width, info.height) == ("h264", 1280, 720)
    assert info.hdr_format == "none" and not info.is_vfr
    assert 55 * 60 < info.duration_s < 65 * 60
    assert "location" not in info.device_hints


def test_portrait_session_keeps_portrait_size() -> None:
    info = probe(_sample("20260928_IMG_1652.MOV"))
    assert (info.width, info.height, info.rotation) == (960, 1280, 0)
    assert output_size(info, 720) == (540, 720)


def test_hdr_session_is_hlg_vfr_and_upside_down() -> None:
    info = probe(_sample("20261012_110549566.mp4"))
    assert info.codec == "hevc" and info.bit_depth == 10
    assert info.hdr_format == "hlg"
    assert info.is_vfr
    assert info.rotation == 180
    assert output_size(info, 720) == (1280, 720)

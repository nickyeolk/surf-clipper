"""Probe the real sample sessions (read-only). Set SURFCLIP_SAMPLES to their folder."""

import os
from pathlib import Path

import pytest

from surfclip.media.probe import probe

SAMPLES = Path(os.environ.get("SURFCLIP_SAMPLES", "/mnt/c/Users/likkhian/OneDrive/Media/trifecta"))

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("name", ["20241004.MP4", "20250326_1.MP4"])
def test_archive_samples_probe_as_720p30_sdr(name: str) -> None:
    path = SAMPLES / name
    if not path.exists():
        pytest.skip(f"{path} not available")
    info = probe(path)
    assert (info.codec, info.width, info.height) == ("h264", 1280, 720)
    assert info.hdr_format == "none"
    assert 55 * 60 < info.duration_s < 65 * 60
    assert "location" not in info.device_hints

"""Decode real and synthetic video (sources read-only)."""

import os
import subprocess
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from surfclip.media.decode import decode_window, iter_proxy_frames
from surfclip.media.probe import probe

SAMPLES = Path(os.environ.get("SURFCLIP_SAMPLES", "/mnt/c/Users/likkhian/OneDrive/Media/trifecta"))
ARCHIVE = SAMPLES / "20241004.MP4"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def archive() -> Path:
    if not ARCHIVE.exists():
        pytest.skip(f"{ARCHIVE} not available")
    return ARCHIVE


def test_proxy_streams_5fps_frames_with_regular_times(archive: Path) -> None:
    info = probe(archive)
    frames = list(iter_proxy_frames(info, fps=5, max_height=720, start_s=600, duration_s=10))
    assert len(frames) == 50
    assert frames[0].image.shape == (720, 1280, 3)
    # Real source frames about every 0.2 s (within one 30 fps source frame).
    assert np.allclose(np.diff([f.pts_s for f in frames]), 0.2, atol=1 / 30)
    assert abs(frames[0].pts_s - 600) < 1 / 30


def test_window_returns_every_source_frame_with_true_times(archive: Path) -> None:
    info = probe(archive)
    frames = decode_window(info, 600.0, 601.0, max_height=720)
    assert len(frames) == 30
    times = [f.pts_s for f in frames]
    assert 600.0 - 1e-3 <= times[0] < 600.0 + 1 / 30
    assert all(b > a for a, b in pairwise(times))
    assert frames[0].index == round(times[0] * 30)


def test_window_frame_matches_proxy_frame_at_same_time(archive: Path) -> None:
    info = probe(archive)
    proxy = next(iter_proxy_frames(info, fps=5, max_height=720, start_s=600, duration_s=1))
    window = decode_window(info, proxy.pts_s - 0.1, proxy.pts_s + 0.1, max_height=720)
    same_time = next(f for f in window if abs(f.pts_s - proxy.pts_s) < 1e-3)
    assert same_time.index == proxy.index
    assert np.array_equal(proxy.image, same_time.image)


def test_hlg_source_is_tonemapped_to_8bit_sdr(tmp_path: Path) -> None:
    src = tmp_path / "hlg.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1920x1080:rate=30",
            "-t",
            "2",
            "-pix_fmt",
            "yuv420p10le",
            "-c:v",
            "libx265",
            "-preset",
            "ultrafast",
            "-x265-params",
            "log-level=error",
            "-color_primaries",
            "bt2020",
            "-color_trc",
            "arib-std-b67",
            "-colorspace",
            "bt2020nc",
            str(src),
        ],
        check=True,
    )
    info = probe(src)
    assert info.hdr_format == "hlg"
    frames = list(iter_proxy_frames(info, fps=5, max_height=720))
    assert len(frames) == 10
    assert frames[0].image.shape == (720, 1280, 3)
    assert frames[0].image.dtype == np.uint8
    assert 10 < frames[0].image.mean() < 245

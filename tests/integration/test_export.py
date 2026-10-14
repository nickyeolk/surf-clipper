"""T032: clip export keeps dynamic range and colour tags, and is frame-accurate."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from surfclip.config import load_config
from surfclip.media.export import export_clip
from surfclip.media.probe import probe
from surfclip.store.schemas import Ride

SAMPLES = Path(os.environ.get("SURFCLIP_SAMPLES", "/mnt/c/Users/likkhian/OneDrive/Media/trifecta"))
pytestmark = pytest.mark.integration
CFG = load_config().export


def _ride(start: float, end: float, fps: float) -> Ride:
    return Ride(
        ride_id="r000001",
        start_s=start,
        end_s=end,
        confidence=0.9,
        start_frame=round(start * fps),
        end_frame=round(end * fps),
        clip_start_s=start - 1.0,
        clip_end_s=end + 1.5,
        epochs=[0],
        track_ids=[1],
    )


def _stream(path: Path) -> dict[str, Any]:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=codec_name,pix_fmt,color_primaries,color_transfer,color_space,nb_read_frames",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)["streams"][0]


def _hdr_source(tmp: Path, trc: str) -> Path:
    src = tmp / f"src_{trc}.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=30",
            "-t",
            "8",
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
            trc,
            "-colorspace",
            "bt2020nc",
            str(src),
        ],
        check=True,
    )
    return src


@pytest.mark.parametrize("cpu", [False, True], ids=["nvenc", "cpu"])
def test_sdr_archive_clip(tmp_path: Path, cpu: bool) -> None:
    src = SAMPLES / "20241004.MP4"
    if not src.exists():
        pytest.skip("sample not available")
    info = probe(src)
    out = tmp_path / "clip.mp4"
    export_clip(info, _ride(600.0, 603.0, info.avg_fps), out, CFG, cpu=cpu)
    s = _stream(out)
    assert s["codec_name"] == "h264" and s["pix_fmt"] == "yuv420p"
    assert s["color_transfer"] == "bt709"
    expected = round((603.0 + 1.5 - 599.0) * info.avg_fps)  # ride + 2.5 s padding
    assert abs(int(s["nb_read_frames"]) - expected) <= 1
    assert info.bit_rate is not None
    size_bits = out.stat().st_size * 8
    assert size_bits / 5.5 <= info.bit_rate * 1.5 * 1.15  # capped near 1.5x source bitrate


@pytest.mark.parametrize("trc", ["arib-std-b67", "smpte2084"], ids=["hlg", "pq"])
def test_hdr_clip_keeps_transfer_and_10_bit(tmp_path: Path, trc: str) -> None:
    info = probe(_hdr_source(tmp_path, trc))
    out = tmp_path / "clip.mp4"
    export_clip(info, _ride(2.0, 4.0, info.avg_fps), out, CFG, cpu=False)
    s = _stream(out)
    assert s["codec_name"] == "hevc"
    assert s["pix_fmt"] == "yuv420p10le"
    assert (s["color_primaries"], s["color_transfer"], s["color_space"]) == (
        "bt2020",
        trc,
        "bt2020nc",
    )
    assert abs(int(s["nb_read_frames"]) - round(4.5 * 30)) <= 1

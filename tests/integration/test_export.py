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


def test_reel_joins_clips_in_order(tmp_path: Path) -> None:
    """Two rides exported and joined into one video without re-encoding (reel)."""
    from datetime import UTC, datetime

    from surfclip.media.export import export_reel
    from surfclip.store.schemas import Rides, Session, SourceSummary
    from surfclip.store.session import SessionStore

    src = tmp_path / "footage" / "src.mp4"
    src.parent.mkdir()
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
         "-t", "20", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", str(src)],
        check=True,
    )  # fmt: skip
    info = probe(src)
    root = tmp_path / "artifacts" / "s1"
    root.mkdir(parents=True)
    store = SessionStore(
        root,
        Session(session_id="s1", source_path=str(src), source_size=1, source_mtime=0,
                created_at=datetime(2026, 10, 15, tzinfo=UTC)),
    )  # fmt: skip
    store.write_model("probe.json", info)
    second, first = _ride(12.0, 15.0, info.avg_fps), _ride(3.0, 5.0, info.avg_fps)
    second = second.model_copy(update={"ride_id": "r000360"})
    rides = Rides(
        session_id="s1",
        source=SourceSummary(path=str(src), fps=info.avg_fps, hdr_format="none"),
        settings={"min_length_s": 1, "pad_before_s": 1.0, "pad_after_s": 1.5},  # type: ignore[arg-type]
        rides=[second, first],
    )
    store.write_model("rides.json", rides)
    reel = export_reel(store, CFG, cpu=True)
    frames = int(_stream(reel)["nb_read_frames"])
    expected = round(((5.0 + 1.5) - (3.0 - 1.0) + (15.0 + 1.5) - (12.0 - 1.0)) * info.avg_fps)
    assert abs(frames - expected) <= 2
    assert {p.name for p in (root / "clips").iterdir()} == {
        "r000001.mp4",
        "r000360.mp4",
        "reel.mp4",
    }

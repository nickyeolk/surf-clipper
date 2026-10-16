"""003 T004/T016: captioned compilations keep HDR, captions stay at reference white, segments
are cached; stills are the exact source frame."""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from surfclip.config import load_config
from surfclip.media.compile import export_compilation, read_compilations
from surfclip.media.probe import probe
from surfclip.store.schemas import Ride, RiderGroup, Riders, Rides, Session, SourceSummary
from surfclip.store.session import SessionStore

pytestmark = pytest.mark.integration
CFG = load_config()


def _source(tmp: Path, hdr: bool) -> Path:
    src = tmp / "footage" / "src.mp4"
    src.parent.mkdir(parents=True)
    tags = (
        ["-pix_fmt", "yuv420p10le", "-c:v", "libx265", "-x265-params", "log-level=error",
         "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc"]
        if hdr
        else ["-pix_fmt", "yuv420p", "-c:v", "libx264"]
    )  # fmt: skip
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:size=640x360:rate=30",
         "-t", "30", "-preset", "ultrafast", *tags, str(src)],
        check=True,
    )  # fmt: skip
    return src


def _ride(rid: str, start: float) -> Ride:
    return Ride(
        ride_id=rid, confidence=0.9, start_s=start, end_s=start + 4, start_frame=round(start * 30),
        end_frame=round((start + 4) * 30), clip_start_s=start - 1, clip_end_s=start + 5,
        epochs=[0], track_ids=[1],
    )  # fmt: skip


def _store(tmp: Path, src: Path) -> SessionStore:
    root = tmp / "artifacts" / "s1"
    root.mkdir(parents=True)
    store = SessionStore(
        root,
        Session(session_id="s1", source_path=str(src), source_size=1, source_mtime=0,
                created_at=datetime(2026, 10, 16, tzinfo=UTC)),
    )  # fmt: skip
    info = probe(src)
    store.write_model("probe.json", info)
    store.write_model(
        "rides.json",
        Rides(
            session_id="s1",
            source=SourceSummary(path=str(src), fps=info.avg_fps, hdr_format=info.hdr_format),
            settings={"min_length_s": 1, "pad_before_s": 1.0, "pad_after_s": 1.0},  # type: ignore[arg-type]
            rides=[_ride("r000600", 20.0), _ride("r000060", 2.0), _ride("r000300", 10.0)],
        ),
    )
    return store


def _riders(name: str) -> Riders:
    return Riders(
        session_id="s1",
        descriptor="embedding",
        riders=[RiderGroup(rider_id="g1", name=name, ride_ids=["r000600", "r000060", "r000300"])],
        assignments=[],
    )


def _ymax(path: Path, start: float, end: float) -> int:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-f", "lavfi",
         "-i", f"movie={path},trim={start}:{end},signalstats",
         "-show_entries", "frame_tags=lavfi.signalstats.YMAX", "-of", "json"],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    frames = json.loads(out)["frames"]
    return max(int(f["tags"]["lavfi.signalstats.YMAX"]) for f in frames)


def _stream(path: Path) -> dict[str, str]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,pix_fmt,color_primaries,color_transfer,color_space:format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    data = json.loads(out)
    return {**data["streams"][0], "duration": data["format"]["duration"]}


def test_hlg_compilation(tmp_path: Path) -> None:
    store = _store(tmp_path, _source(tmp_path, hdr=True))
    # A black test video has a tiny bitrate; the usual cap (1.5x source) would starve the encoder
    # and ring at the text edges, which real footage never does.
    uncapped = CFG.export.model_copy(update={"max_bitrate_factor": 1000.0})
    out = export_compilation(store, uncapped, CFG.compilation, _riders("me"), "me")
    s = _stream(out)
    assert (s["codec_name"], s["pix_fmt"]) == ("hevc", "yuv420p10le")
    assert (s["color_primaries"], s["color_transfer"], s["color_space"]) == (
        "bt2020", "arib-std-b67", "bt2020nc",
    )  # fmt: skip
    assert abs(float(s["duration"]) - 3 * 6.0) < 0.3
    comp = read_compilations(store).compilations["me"]
    assert [r.ride_id for r in comp.rides] == ["r000060", "r000300", "r000600"]
    assert comp.rides[1].caption == "me · ride 2 of 3 · 0:10"
    assert comp.rides[1].offset_s == pytest.approx(6.0, abs=0.1)
    # Caption at most HLG reference white (75% of 64..940 in 10 bit), and gone after caption_s.
    ref_white = 64 + 0.75 * 876
    with_caption = _ymax(out, 0.5, 2.5)
    assert ref_white - 40 < with_caption <= ref_white + 20  # small encoder overshoot at edges
    assert _ymax(out, CFG.compilation.caption_s + 0.2, 5.5) < 120


def test_segments_cached_and_recaptioned_on_rename(tmp_path: Path) -> None:
    store = _store(tmp_path, _source(tmp_path, hdr=False))
    export_compilation(store, CFG.export, CFG.compilation, _riders("me"), "me", cpu=True)
    seg = store.path("clips/captioned/r000060.mp4")
    first = seg.stat().st_mtime_ns
    calls: list[str] = []
    export_compilation(
        store, CFG.export, CFG.compilation, _riders("me"), "me", cpu=True,
        progress=lambda i, n, rid: calls.append(rid),
    )  # fmt: skip
    assert calls == ["joining"] and seg.stat().st_mtime_ns == first
    export_compilation(store, CFG.export, CFG.compilation, _riders("jo"), "jo", cpu=True)
    assert seg.stat().st_mtime_ns != first
    assert store.path("clips/reel_jo.mp4").exists()


def _frame(src: Path, n: int, hdr: bool) -> np.ndarray:
    """Frame n of the source (decoded from the start, no seeking), as the still would show it."""
    from surfclip.media.review import TONEMAP

    vf = [
        *([TONEMAP] if hdr else []),
        f"select=eq(n\\,{n})",
        "scale=in_color_matrix=auto,format=rgb24",
    ]
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(src), "-vf", ",".join(vf), "-frames:v", "1",
         "-f", "rawvideo", "-"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
    return np.frombuffer(raw, np.uint8).reshape(360, 640, 3).astype(np.float32)


@pytest.mark.parametrize("hdr", [False, True], ids=["sdr", "hlg"])
def test_still_is_the_exact_source_frame(tmp_path: Path, hdr: bool) -> None:
    from PIL import Image

    from surfclip.media.stills import read_stills, save_still

    src = tmp_path / "footage" / "src.mp4"
    src.parent.mkdir(parents=True)
    tags = (
        ["-pix_fmt", "yuv420p10le", "-c:v", "libx265", "-x265-params", "log-level=error",
         "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc"]
        if hdr
        else ["-pix_fmt", "yuv420p", "-c:v", "libx264"]
    )  # fmt: skip
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
         "-t", "20", "-preset", "ultrafast", "-g", "60", *tags, str(src)],
        check=True,
    )  # fmt: skip
    store = _store(tmp_path, src)
    still, created = save_still(store, CFG.compilation, 12.34)  # frame 370, inside ride r000300
    assert created and (still.frame, still.ride_id) == (370, "r000300")
    assert (still.width, still.height) == (640, 360)
    img = np.asarray(Image.open(store.path(still.path)).convert("RGB"), np.float32)
    errors = {n: float(np.abs(img - _frame(src, n, hdr)).mean()) for n in (369, 370, 371)}
    assert min(errors, key=lambda n: errors[n]) == 370
    assert errors[370] < 4.0  # JPEG and chroma subsampling only
    again, created = save_still(store, CFG.compilation, 12.335)
    assert not created and again.name == still.name == "r000300_f000370.jpg"
    assert len(read_stills(store).stills) == 1

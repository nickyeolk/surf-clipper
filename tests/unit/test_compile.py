"""003 T003: captions, caption filter and segment cache keys."""

from pathlib import Path

from surfclip.config import load_config
from surfclip.media.compile import (
    caption_filter,
    captions,
    clock,
    find_rider,
    segment_key,
    text_colour,
)
from surfclip.store.schemas import (
    Ride,
    RiderGroup,
    Riders,
    Rides,
    SourceInfo,
    SourceSummary,
)

CFG = load_config()


def _info(hdr: str = "none", w: int = 1920, h: int = 1080) -> SourceInfo:
    return SourceInfo(
        path="/v/src.mp4", container="mp4", codec="hevc", width=w, height=h, duration_s=3600,
        avg_fps=30.0, is_vfr=False, bit_depth=10, pix_fmt="yuv420p10le",
        hdr_format=hdr,  # type: ignore[arg-type]
    )  # fmt: skip


def _ride(rid: str, start: float) -> Ride:
    return Ride(
        ride_id=rid, confidence=0.9, start_s=start, end_s=start + 10, start_frame=0, end_frame=0,
        clip_start_s=start - 1.5, clip_end_s=start + 12, epochs=[0], track_ids=[1],
    )  # fmt: skip


def _rides(*rides: Ride) -> Rides:
    return Rides(
        session_id="s",
        source=SourceSummary(path="/v/src.mp4", fps=30.0, hdr_format="none"),
        settings={"min_length_s": 1, "pad_before_s": 1.5, "pad_after_s": 2.0},  # type: ignore[arg-type]
        rides=list(rides),
    )


def _riders() -> Riders:
    return Riders(
        session_id="s",
        descriptor="embedding",
        riders=[
            RiderGroup(rider_id="g1", name="me", ride_ids=["r3", "r1", "r2"]),
            RiderGroup(rider_id="g2", ride_ids=["r4"]),
        ],
        assignments=[],
    )


def test_clock() -> None:
    assert clock(0) == "0:00"
    assert clock(642.7) == "10:42"
    assert clock(3725) == "1:02:05"


def test_captions_number_rides_in_time_order() -> None:
    rides = _rides(_ride("r3", 900), _ride("r1", 100), _ride("r2", 500), _ride("r4", 50))
    caps = captions(rides, "me", ["r3", "r1", "r2"])
    assert [c.ride_id for c in caps] == ["r1", "r2", "r3"]
    assert caps[2].text == "me · ride 3 of 3 · 15:00"


def test_unnamed_rider_gets_rider_n() -> None:
    label, ids = find_rider(_riders(), "g2")
    assert (label, ids) == ("Rider 2", ["r4"])
    assert find_rider(_riders(), "me")[0] == "me"


def test_text_level_is_reference_white_grey() -> None:
    assert text_colour(_info("hlg"), CFG.compilation) == "0xBFBFBF"  # 0.75
    assert text_colour(_info("hdr10"), CFG.compilation) == "0x949494"  # 0.58
    assert text_colour(_info("none"), CFG.compilation) == "0xEBEBEB"  # 0.92


def test_caption_filter_sizes_from_shorter_side_and_quotes_paths() -> None:
    landscape = caption_filter(_info(), CFG.compilation, Path("/a:b/it's.txt"))
    portrait = caption_filter(_info(w=1080, h=1920), CFG.compilation, Path("/x.txt"))
    size = round(1080 * CFG.compilation.size_frac)
    assert f"fontsize={size}:" in landscape and f"fontsize={size}:" in portrait
    assert "textfile='/a:b/it'\\''s.txt'" in landscape
    assert "expansion=none" in landscape
    assert f"enable='lt(t,{CFG.compilation.caption_s:.3f})'" in landscape


def test_segment_key_follows_caption_and_settings_only() -> None:
    info, ride = _info(), _ride("r1", 100)
    base = segment_key(info, ride, CFG.export, CFG.compilation, False, "me · ride 1 of 2 · 1:40")
    renamed = segment_key(info, ride, CFG.export, CFG.compilation, False, "jo · ride 1 of 2 · 1:40")
    bigger = CFG.compilation.model_copy(update={"size_frac": 0.08})
    resized = segment_key(info, ride, CFG.export, bigger, False, "me · ride 1 of 2 · 1:40")
    same = segment_key(info, ride, CFG.export, CFG.compilation, False, "me · ride 1 of 2 · 1:40")
    assert base == same
    assert len({base, renamed, resized}) == 3

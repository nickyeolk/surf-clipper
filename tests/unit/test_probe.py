from typing import Any

import pytest

from surfclip.media.probe import UnsupportedInputError, parse_probe


def _probe(video: dict[str, Any], duration: str = "3764.1", **fmt_tags: str) -> dict[str, Any]:
    base = {"codec_type": "video", "width": 1280, "height": 720, "pix_fmt": "yuv420p"}
    return {
        "streams": [
            {"codec_type": "audio", "codec_name": "aac"},
            base | video,
            {"codec_type": "data", "tags": {"handler_name": "Core Media Metadata"}},
        ],
        "format": {"format_name": "mov,mp4", "duration": duration, "tags": fmt_tags},
    }


ARCHIVE = {  # shape of the 720p30 iPhone export archive (20241004.MP4)
    "codec_name": "h264",
    "profile": "High",
    "color_space": "bt709",
    "color_transfer": "bt709",
    "color_primaries": "bt709",
    "r_frame_rate": "30/1",
    "avg_frame_rate": "30/1",
    "bits_per_raw_sample": "8",
    "nb_frames": "112923",
    "tags": {"handler_name": "Core Media Video"},
}


def test_archive_file_is_sdr_cfr_with_audio_first() -> None:
    info = parse_probe("a.MP4", _probe(ARCHIVE, location="+01.30+103.83/"))
    assert (info.codec, info.width, info.height, info.avg_fps) == ("h264", 1280, 720, 30.0)
    assert info.hdr_format == "none" and not info.is_vfr and info.bit_depth == 8
    assert info.frame_count == 112923 and info.has_audio


def test_location_tag_is_never_copied() -> None:
    info = parse_probe("a.MP4", _probe(ARCHIVE, location="+01.30+103.83/"))
    assert "location" not in info.device_hints
    assert info.device_hints == {"handler_name": "Core Media Video"}


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ({"color_transfer": "arib-std-b67"}, "hlg"),
        ({"color_transfer": "smpte2084"}, "hdr10"),
        ({"color_transfer": "arib-std-b67", "codec_tag_string": "dvh1"}, "dolby_vision"),
        (
            {"side_data_list": [{"side_data_type": "DOVI configuration record"}]},
            "dolby_vision",
        ),
    ],
)
def test_hdr_formats(extra: dict[str, Any], expected: str) -> None:
    video = {
        "codec_name": "hevc",
        "pix_fmt": "yuv420p10le",
        "avg_frame_rate": "30/1",
        "r_frame_rate": "30/1",
        "color_primaries": "bt2020",
    } | extra
    info = parse_probe("h.MOV", _probe(video))
    assert info.hdr_format == expected
    assert info.bit_depth == 10


def test_variable_frame_rate_and_missing_frame_count() -> None:
    video = {"codec_name": "h264", "avg_frame_rate": "29970/1000", "r_frame_rate": "30/1"}
    info = parse_probe("v.MP4", _probe(video, duration="60"))
    assert info.is_vfr
    assert info.frame_count == round(60 * 29.97)


def test_rotation_from_display_matrix() -> None:
    video = {
        "codec_name": "hevc",
        "avg_frame_rate": "60/1",
        "r_frame_rate": "60/1",
        "side_data_list": [{"side_data_type": "Display Matrix", "rotation": -90}],
    }
    assert parse_probe("r.MOV", _probe(video)).rotation == 270


def test_too_long_is_rejected_with_clear_message() -> None:
    with pytest.raises(UnsupportedInputError, match=r"longer than the 1\.5 h limit"):
        parse_probe("long.MP4", _probe(ARCHIVE, duration=str(1.6 * 3600)))


def test_unsupported_codec_is_rejected() -> None:
    with pytest.raises(UnsupportedInputError, match="'prores' is not supported"):
        parse_probe("p.MOV", _probe(ARCHIVE | {"codec_name": "prores"}))


def test_no_video_stream_is_rejected() -> None:
    data = {"streams": [{"codec_type": "audio"}], "format": {"duration": "10"}}
    with pytest.raises(UnsupportedInputError, match="no video stream"):
        parse_probe("a.m4a", data)

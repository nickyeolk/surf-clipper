"""Versioned configuration (constitution IX).

Defaults live in config/default.toml. A session may override individual keys with dotted
names such as ``rides.min_length_s``. Every stage's cache key includes ``config_version``
and the hash of the config sections it reads, so a changed threshold re-runs only the
stages that depend on it.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "default.toml"


class ConfigError(ValueError):
    """Raised for unreadable files, unknown keys or invalid values."""


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AnalysisConfig(_Section):
    fps: int
    max_height: int
    tonemap: str


class DetectConfig(_Section):
    model: str
    confidence: float
    classes: list[str]
    half_precision: bool
    batch_size: int
    tiling: Literal["off", "auto", "always"]
    tiling_min_height_px_at_720p: int
    tile_overlap_frac: float
    imgsz: int
    nms_iou: float


class TrackConfig(_Section):
    max_gap_s: float
    min_track_s: float
    match_iou: float
    assoc_box_scale: float
    edge_margin_frac: float
    sitting_max_aspect: float
    crouched_max_aspect: float
    board_reach_heights: float


class EpochsConfig(_Section):
    match_fps: float
    features: Literal["orb", "sift"]
    jump_frac: float
    drift_frac: float
    min_inliers: int
    min_inlier_ratio: float


class ZoneConfig(_Section):
    proposal_min_tracks: int
    proposal_min_confidence: float
    try_both_orientations: bool
    undistort_ultrawide: Literal["off", "auto"]


class RidesConfig(_Section):
    confirm_window_s: float
    min_lateral_speed_pool: float
    evidence_gap_s: float
    wall_band_in_pool: float
    wall_band_out_pool: float
    zone_margin_pool: float
    acid_link_s: float
    acid_link_heights: float
    lesson_overlap_frac: float
    stitch_gap_s: float
    stitch_base_heights: float
    stitch_heights_per_s: float
    frame_edge_grace_s: float
    min_length_s: float
    pad_before_s: float
    pad_after_s: float
    refine_window_s: float
    changeover_overlap_max_s: float


class ExportConfig(_Section):
    encoder: Literal["auto", "nvenc", "cpu"]
    hdr_codec: str
    sdr_codec: str
    nvenc_preset: str
    cq: int


class ReviewConfig(_Section):
    height: int
    keyframe_interval_s: float
    thumb_every_s: float


class ServerConfig(_Section):
    host: str
    port: int

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, v: str) -> str:
        if v not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("server.host must be a loopback address (FR-025)")
        return v


class Config(_Section):
    config_version: int
    analysis: AnalysisConfig
    detect: DetectConfig
    track: TrackConfig
    epochs: EpochsConfig
    zone: ZoneConfig
    rides: RidesConfig
    export: ExportConfig
    review: ReviewConfig
    server: ServerConfig

    def section_hash(self, section: str) -> str:
        """Stable hash of one section's values, for stage cache keys.

        Only the section's own values count: a change to ride thresholds must never re-run
        detection (FR-023). ``config_version`` is informational and deliberately left out.
        """
        part = getattr(self, section)
        assert isinstance(part, BaseModel)
        payload = json.dumps({section: part.model_dump(mode="json")}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _apply_override(data: dict[str, Any], dotted: str, value: object) -> None:
    *parents, leaf = dotted.split(".")
    node: dict[str, Any] = data
    for key in parents:
        child: object = node.get(key)
        if not isinstance(child, dict):
            raise ConfigError(f"unknown config key: {dotted}")
        node = cast(dict[str, Any], child)
    if leaf not in node:
        raise ConfigError(f"unknown config key: {dotted}")
    node[leaf] = value


def load_config(
    path: Path = DEFAULT_CONFIG_PATH, overrides: dict[str, object] | None = None
) -> Config:
    try:
        data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    for key, value in (overrides or {}).items():
        _apply_override(data, key, value)
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        msg = str(exc)
        if "loopback" in msg:
            raise ConfigError("server.host must be a loopback address (FR-025)") from exc
        raise ConfigError(msg) from exc

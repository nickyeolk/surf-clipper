"""Typed models for the session files in contracts/session-files.md.

``rides.json`` and ``edits.json`` are public contracts read by features 002 and 003: change
their shape only with a ``schema_version`` bump (major for breaking changes).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0.0"

Point = tuple[float, float]
Matrix3 = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]
RideState = Literal["off", "dropping_in", "on_wave"]
StageName = Literal[
    "probe",
    "proxy",
    "review_copy",
    "detect",
    "track",
    "epochs",
    "zone_proposal",
    "rides",
    "refine",
    "apply_edits",
    "export",
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Versioned(_Model):
    schema_version: str = SCHEMA_VERSION


# --- session.json ---------------------------------------------------------------------------


class StageStatus(_Model):
    status: Literal["pending", "running", "done", "failed"] = "pending"
    cache_key: str | None = None
    outputs: list[str] = Field(default_factory=list[str])
    finished_at: datetime | None = None
    error: str | None = None


class Session(_Versioned):
    session_id: str
    source_path: str
    source_size: int
    source_mtime: float
    created_at: datetime
    config_overrides: dict[str, object] = Field(default_factory=dict[str, object])
    stages: dict[StageName, StageStatus] = Field(default_factory=dict[StageName, StageStatus])


# --- probe.json -----------------------------------------------------------------------------


class SourceInfo(_Versioned):
    path: str
    container: str
    codec: str
    profile: str | None = None
    width: int
    height: int
    duration_s: float
    frame_count: int | None = None
    avg_fps: float
    is_vfr: bool
    bit_depth: int
    pix_fmt: str
    color_primaries: str | None = None
    color_transfer: str | None = None
    color_space: str | None = None
    hdr_format: Literal["none", "hlg", "hdr10", "dolby_vision"]
    rotation: int = 0
    has_audio: bool = False
    device_hints: dict[str, str] = Field(default_factory=dict[str, str])


# --- epochs.json / zones.json ---------------------------------------------------------------


class CameraEpoch(_Model):
    epoch_id: int
    start_s: float
    end_s: float
    reference_frame: int
    transform_from_prev: Matrix3 | None = None
    inlier_ratio: float | None = None
    inliers: int | None = None
    cause: Literal["start", "jump", "drift"]
    remap: Literal["none", "auto", "needs_confirmation"] = "none"


class Epochs(_Versioned):
    epochs: list[CameraEpoch]


class ZoneCorners(_Model):
    """Corners by role, never by image side (constitution III)."""

    deck_a: Point
    deck_b: Point
    wave_end_a: Point
    wave_end_b: Point


class Zone(_Model):
    epoch_id: int
    corners: ZoneCorners
    deck_boundary: list[Point]
    entrance: list[list[Point]] = Field(default_factory=list[list[Point]])
    side_areas: list[list[Point]] = Field(default_factory=list[list[Point]])
    image_to_pool: Matrix3 | None = None
    undistort: dict[str, float] | None = None
    origin: Literal["proposed", "auto_remap", "user"]
    proposal_confidence: float | None = None


class Zones(_Versioned):
    zones: list[Zone]


# --- rides.json -----------------------------------------------------------------------------


class RideFlags(_Model):
    lesson: bool = False
    truncated: bool = False
    user_edited: bool = False
    user_added: bool = False


class ExportRecord(_Model):
    path: str
    cache_key: str
    exported_at: datetime


class _RideSpan(_Model):
    ride_id: str
    start_s: float
    end_s: float
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _end_after_start(self) -> _RideSpan:
        if self.end_s <= self.start_s:
            raise ValueError(f"{self.ride_id}: end_s must be after start_s")
        return self


class Ride(_RideSpan):
    start_frame: int
    end_frame: int
    clip_start_s: float
    clip_end_s: float
    epochs: list[int]
    track_ids: list[int]
    start_kind: Literal["entrance", "acid_drop", "unknown"] = "unknown"
    state_timeline: list[tuple[float, RideState]] = Field(
        default_factory=list[tuple[float, RideState]]
    )
    flags: RideFlags = Field(default_factory=RideFlags)
    export: ExportRecord | None = None

    @property
    def length_s(self) -> float:
        return self.end_s - self.start_s


class ShortAttempt(_RideSpan):
    pass


class SourceSummary(_Model):
    path: str
    fps: float
    hdr_format: Literal["none", "hlg", "hdr10", "dolby_vision"]


class RideSettings(_Model):
    min_length_s: float
    pad_before_s: float
    pad_after_s: float


class Marker(_Model):
    t_s: float
    kind: Literal["remap"]
    epoch_id: int


class Rides(_Versioned):
    session_id: str
    source: SourceSummary
    settings: RideSettings
    rides: list[Ride]
    short_attempts: list[ShortAttempt] = Field(default_factory=list[ShortAttempt])
    markers: list[Marker] = Field(default_factory=list[Marker])

    @model_validator(mode="after")
    def _min_length_unless_user_added(self) -> Rides:
        """Rides >= min_length_s unless user_added (data-model.md)."""
        for ride in self.rides:
            if ride.length_s < self.settings.min_length_s and not ride.flags.user_added:
                raise ValueError(
                    f"{ride.ride_id}: {ride.length_s:.2f}s is shorter than min_length_s "
                    f"{self.settings.min_length_s}s and not user_added"
                )
        return self


# --- edits.json -----------------------------------------------------------------------------


class EditTarget(_Model):
    epoch_id: int | None = None
    ride_id: str | None = None
    ride_ids: list[str] | None = None


EditOp = Literal["confirm_zone", "trim", "split", "merge", "delete", "add"]


class UserEdit(_Model):
    edit_id: Annotated[int, Field(ge=1)]
    at: datetime
    op: EditOp
    target: EditTarget
    payload: dict[str, object] = Field(default_factory=dict[str, object])


class Edits(_Versioned):
    edits: list[UserEdit] = Field(default_factory=list[UserEdit])

    @model_validator(mode="after")
    def _sequential_ids(self) -> Edits:
        ids = [e.edit_id for e in self.edits]
        if ids != list(range(1, len(ids) + 1)):
            raise ValueError("edit_id values must be 1..n in order (append-only log)")
        return self

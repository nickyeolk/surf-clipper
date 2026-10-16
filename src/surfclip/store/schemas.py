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
    "riders",
    "analysis",
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
    bit_rate: int | None = None  # video bits per second, when known
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
    """Image positions of the wave zone's corners, by role (constitution III).

    ``back_*`` are the two ends of the back wall; ``front_*`` the front ends of the side walls.
    Side wall ``a`` runs back_a -> front_a, side wall ``b`` runs back_b -> front_b. Which side
    is ``a`` is arbitrary, never tied to image left or right. Corners may lie outside the frame.
    """

    back_a: Point
    back_b: Point
    front_a: Point
    front_b: Point


SideWall = Literal["side_a", "side_b"]


class Zone(_Model):
    epoch_id: int
    corners: ZoneCorners
    entry_walls: list[SideWall] = Field(default_factory=lambda: ["side_a", "side_b"])
    side_areas: list[list[Point]] = Field(default_factory=list[list[Point]])  # waiting, image px
    face_v: tuple[float, float] | None = None  # wave face as pool-depth band; None = estimate
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
    joined: bool = False  # 002: two rides split at the frame edge, joined automatically


class ExportRecord(_Model):
    path: str  # relative to the session folder
    cache_key: str
    exported_at: datetime
    span: tuple[float, float]  # clip_start_s, clip_end_s the clip was cut with


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
    start_kind: Literal["step_in", "acid_drop", "off_frame", "unknown"] = "unknown"
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
        """Rides >= min_length_s unless the user added or edited them (data-model.md)."""
        for ride in self.rides:
            user_made = ride.flags.user_added or ride.flags.user_edited
            if ride.length_s < self.settings.min_length_s and not user_made:
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


EditOp = Literal[
    "confirm_zone",
    "trim",
    "split",
    "merge",
    "delete",
    "add",
    "undo",
    # 002: rider edits, anchored to rides by span (never to group ids)
    "rider_name",
    "rider_same_as",
    "rider_mixed",
    "rider_ignore",
    "ride_rider",
    "rider_unjoin",
    # 004: analysis corrections and trick tags, anchored to rides by span
    "ride_ending",
    "turn_add",
    "turn_remove",
    "trick_tag",
]


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


# --- riders.json (002) ----------------------------------------------------------------------


class RiderStill(_Model):
    ride_id: str
    t_s: float


class RiderGroup(_Model):
    rider_id: str  # stable within one computation only; never stored in edits
    name: str | None = None
    ignored: bool = False
    kind: Literal["rider", "lesson"] = "rider"
    ride_ids: list[str]
    example_ride_id: str | None = None
    stills: list[RiderStill] = Field(default_factory=list[RiderStill])


class RideAssignment(_Model):
    ride_id: str
    rider_id: str | None  # None: no rider (e.g. a hand-added ride without a person)
    confidence: float = Field(ge=0.0, le=1.0)
    confirmed: bool = False
    queued: bool = False
    low_evidence: bool = False


class JoinSuggestion(_Model):
    first: str
    second: str
    gap_s: float
    confidence: float = Field(ge=0.0, le=1.0)


class Riders(_Versioned):
    session_id: str
    descriptor: Literal["colour", "embedding", "both"]
    riders: list[RiderGroup]
    assignments: list[RideAssignment]
    join_suggestions: list[JoinSuggestion] = Field(default_factory=list[JoinSuggestion])
    auto_joined: list[tuple[str, str]] = Field(default_factory=list[tuple[str, str]])


RideRef = tuple[str, float, float]  # ride id, start s, end s (re-attached by time overlap)


class AutoJoins(_Versioned):
    """Rides split at the frame edge that the riders stage joined (002, research R7). A stage
    output, not an edit: rides.json applies them; the user's ``rider_unjoin`` edits win."""

    joins: list[tuple[RideRef, RideRef]] = Field(default_factory=list[tuple[RideRef, RideRef]])


class CaptionedSegment(_Model):
    """One ride re-encoded with its caption for a compilation (003, research R2)."""

    path: str
    cache_key: str
    span: tuple[float, float]
    duration_s: float


class CompilationRide(_Model):
    ride_id: str
    offset_s: float  # start of this ride in the compilation
    duration_s: float
    clip_start_s: float  # source time of the segment's first frame
    caption: str


class Compilation(_Model):
    rider: str  # display name at export time (rider ids are not stable across recomputes)
    path: str
    made_at: datetime
    rides: list[CompilationRide]


class Compilations(_Versioned):
    segments: dict[str, CaptionedSegment] = Field(default_factory=dict[str, CaptionedSegment])
    compilations: dict[str, Compilation] = Field(default_factory=dict[str, Compilation])


class Still(_Model):
    name: str
    path: str
    t_s: float  # source time, on the frame grid
    frame: int
    ride_id: str | None = None
    rider: str | None = None
    width: int
    height: int
    saved_at: datetime


class Stills(_Versioned):
    stills: list[Still] = Field(default_factory=list[Still])


# --- 004: analysis.json ---------------------------------------------------------------------

Ending = Literal["fall", "exit", "unclear"]


class AnalysisEvent(_Model):
    t: float
    depth: float | None = None  # compression at the event (1 = ride median)
    side: str | None = None
    name: str | None = None  # trick tags
    by: Literal["auto", "user"] = "auto"


class RideShares(_Model):
    turning: float = 0.0
    pumping: float = 0.0
    trimming: float = 0.0
    unclear: float = 0.0


class RideSummary(_Model):
    length_s: float
    turns: int = 0
    pumps: int = 0
    turn_rate_per_10s: float = 0.0
    rhythm_cv: float | None = None
    mean_depth: float | None = None


class RideAnalysis(_Model):
    ride_id: str
    span: tuple[float, float]
    rider: str
    cache_key: str
    keypoints_key: str  # the part of the key the keypoints depend on (span + pose settings)
    fps: float
    t0: float  # time of the first analysed frame
    compression: list[float | None] = Field(default_factory=list[float | None])
    lateral: list[float | None] = Field(default_factory=list[float | None])
    turns: list[AnalysisEvent] = Field(default_factory=list[AnalysisEvent])
    pumps: list[AnalysisEvent] = Field(default_factory=list[AnalysisEvent])
    shares: RideShares = Field(default_factory=RideShares)
    ending: Ending = "unclear"
    ending_auto: Ending = "unclear"
    summary: RideSummary
    tricks: list[AnalysisEvent] = Field(default_factory=list[AnalysisEvent])  # user trick tags


class AnalysisFile(_Versioned):
    session_id: str
    settings: dict[str, object] = Field(default_factory=dict[str, object])
    rides: list[RideAnalysis] = Field(default_factory=list[RideAnalysis])

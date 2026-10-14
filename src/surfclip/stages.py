"""Concrete pipeline stages, in run order (plan.md; constitution VII).

probe -> detect -> track -> rides. Epochs, zone proposal and refinement are added by later tasks.
Until zone proposal exists (US2), the rides stage needs a zone confirmed with
``surfclip zone SESSION --from-file``.
"""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel

from surfclip.config import RidesConfig
from surfclip.edits.apply import apply_edits
from surfclip.edits.log import confirmed_zone, read_edits
from surfclip.media.decode import Frame, iter_proxy_frames, output_size
from surfclip.media.export import attach_exports, read_exports
from surfclip.media.probe import probe
from surfclip.media.review import make_review_copy
from surfclip.pipeline import Pipeline, Stage, StageContext
from surfclip.rides.assemble import assemble
from surfclip.rides.evidence import Evidence, Obs, classify, to_source_pixels
from surfclip.rides.face import FaceBand, estimate_face
from surfclip.rides.state_machine import TrackRide, track_rides
from surfclip.rides.stitch import stitch
from surfclip.store.frames import (
    FrameMeta,
    read_detections,
    read_meta,
    read_observations,
    write_detections,
    write_observations,
)
from surfclip.store.schemas import (
    Rides,
    RideSettings,
    SourceInfo,
    SourceSummary,
    StageName,
    Zone,
)
from surfclip.store.session import SessionStore
from surfclip.track.tracker import AnalysedFrame, track_people

if TYPE_CHECKING:  # the detector pulls in torch and YOLO; import it only when detection runs
    from surfclip.detect.detector import Detector

log = logging.getLogger(__name__)


class ZoneNotConfirmedError(RuntimeError):
    pass


@dataclass
class ProbeStage(Stage):
    name: StageName = "probe"
    depends_on: tuple[StageName, ...] = ()
    config_sections: tuple[str, ...] = ()
    code_version: str = "1"

    def run(self, ctx: StageContext) -> list[str]:
        ctx.store.write_model("probe.json", probe(ctx.store.source))
        return ["probe.json"]


@dataclass
class ReviewCopyStage(Stage):
    name: StageName = "review_copy"
    depends_on: tuple[StageName, ...] = ("probe",)
    config_sections: tuple[str, ...] = ("review",)
    code_version: str = "1"
    cpu: bool = False

    def run(self, ctx: StageContext) -> list[str]:
        info = ctx.store.read_model("probe.json", SourceInfo)
        make_review_copy(info, ctx.store.path("review.mp4"), ctx.config.review, cpu=self.cpu)
        return ["review.mp4"]


@dataclass
class DetectStage(Stage):
    name: StageName = "detect"
    depends_on: tuple[StageName, ...] = ("probe",)
    config_sections: tuple[str, ...] = ("analysis", "detect")
    code_version: str = "1"
    cpu: bool = False
    chunk: int = 64

    def run(self, ctx: StageContext) -> list[str]:
        from surfclip.detect.detector import Detector  # loads torch/YOLO only when needed

        info = ctx.store.read_model("probe.json", SourceInfo)
        a = ctx.config.analysis
        width, height = output_size(info, a.max_height)
        detector = Detector(ctx.config.detect, cpu=self.cpu)
        total = max(1, round(info.duration_s * a.fps))
        started = time.perf_counter()

        def analysed() -> Iterator[AnalysedFrame]:
            buf: list[Frame] = []
            done = 0
            for fr in iter_proxy_frames(
                info, fps=a.fps, max_height=a.max_height, tonemap=a.tonemap
            ):
                buf.append(fr)
                if len(buf) == self.chunk:
                    yield from _detect_chunk(detector, buf)
                    done += len(buf)
                    buf = []
                    if done % (self.chunk * 20) == 0:
                        rate = done / (time.perf_counter() - started)
                        log.info("detect %d/%d frames (%.0f/s)", done, total, rate)
            yield from _detect_chunk(detector, buf)

        write_detections(
            ctx.store.path("detections.parquet"), analysed(), FrameMeta(width, height, a.fps)
        )
        return ["detections.parquet"]


def _detect_chunk(detector: Detector, frames: list[Frame]) -> Iterator[AnalysedFrame]:
    if not frames:
        return
    for fr, det in zip(frames, detector.detect([f.image for f in frames]), strict=True):
        yield AnalysedFrame(t=fr.pts_s, frame=fr.index, detections=det)


@dataclass
class TrackStage(Stage):
    name: StageName = "track"
    depends_on: tuple[StageName, ...] = ("detect",)
    config_sections: tuple[str, ...] = ("track",)
    code_version: str = "1"

    def run(self, ctx: StageContext) -> list[str]:
        src = ctx.store.path("detections.parquet")
        meta = read_meta(src)
        obs = track_people(
            read_detections(src),
            width=meta.width,
            height=meta.height,
            fps=meta.fps,
            cfg=ctx.config.track,
        )
        write_observations(ctx.store.path("tracks.parquet"), obs, meta)
        return ["tracks.parquet"]


@dataclass
class RidesStage(Stage):
    name: StageName = "rides"
    depends_on: tuple[StageName, ...] = ("track",)
    config_sections: tuple[str, ...] = ("rides",)
    code_version: str = "6"  # 6: face band, horizon; 5: activity; 4: truncated; 3: px; 2: stitch

    def extra_inputs(self, store: SessionStore) -> list[str]:
        # The confirmed zone and every ride edit change rides.json; this stage is cheap.
        return [f"edits:{read_edits(store).model_dump_json()}"]

    def run(self, ctx: StageContext) -> list[str]:
        store, cfg = ctx.store, ctx.config.rides
        zone = confirmed_zone(read_edits(store))
        if zone is None:
            raise ZoneNotConfirmedError(
                "no confirmed zone: run `surfclip zone <video> --from-file zone.json` first"
            )
        info = store.read_model("probe.json", SourceInfo)
        tracks_file = store.path("tracks.parquet")
        sx, sy = source_scale(info, read_meta(tracks_file))
        by_track: dict[int, list[Obs]] = defaultdict(list)
        for o in to_source_pixels(read_observations(tracks_file), sx, sy):
            by_track[o.track_id].append(o)
        chains, members = stitch(list(by_track.values()), cfg)
        face = self._face(chains, zone, cfg)
        store.write_model("face.json", face)
        evidence: dict[int, list[Evidence]] = {
            cid: classify(obs, zone, cfg, face=face.face_v) for cid, obs in chains.items()
        }
        store.write_model(
            "activity.json", activity(evidence, info.duration_s, read_meta(tracks_file).fps)
        )
        trs: list[TrackRide] = [r for evs in evidence.values() for r in track_rides(evs, cfg)[1]]
        rides, short = assemble(
            trs, evidence, cfg=cfg, fps=info.avg_fps, duration_s=info.duration_s
        )
        rides = [  # report the tracker's own fragment ids, not chain ids
            r.model_copy(update={"track_ids": [t for c in r.track_ids for t in members[c]]})
            for r in rides
        ]
        detected = Rides(
            session_id=store.session.session_id,
            source=SourceSummary(path=info.path, fps=info.avg_fps, hdr_format=info.hdr_format),
            settings=RideSettings(
                min_length_s=cfg.min_length_s,
                pad_before_s=cfg.pad_before_s,
                pad_after_s=cfg.pad_after_s,
            ),
            rides=rides,
            short_attempts=short,
        )
        store.write_model("rides.detected.json", detected)
        edited = apply_edits(detected, read_edits(store))
        store.write_model("rides.json", attach_exports(edited, read_exports(store), store))
        return ["rides.detected.json", "rides.json", "activity.json", "face.json"]

    @staticmethod
    def _face(chains: dict[int, list[Obs]], zone: Zone, cfg: RidesConfig) -> FaceBand:
        """The user's face band if set, else estimated from a first pass without one."""
        if zone.face_v is not None:
            return FaceBand(face_v=zone.face_v, origin="zone", frames=0)
        on_wave_v: list[float] = []
        for obs in chains.values():
            evs = classify(obs, zone, cfg)
            states, _ = track_rides(evs, cfg)
            on_wave_v += [
                ev.v for ev, st in zip(evs, states, strict=True) if st == "on_wave" and ev.candidate
            ]
        return estimate_face(on_wave_v, cfg)


class Activity(BaseModel):
    """Share of analysed frames per bin with someone riding (review timeline strip)."""

    bin_s: float
    values: list[float]


def activity(
    evidence: dict[int, list[Evidence]], duration_s: float, fps: float, bin_s: float = 1.0
) -> Activity:
    n = max(1, math.ceil(duration_s / bin_s))
    seen: list[set[float]] = [set() for _ in range(n)]
    for evs in evidence.values():
        for ev in evs:
            if ev.candidate:
                seen[min(n - 1, int(ev.t / bin_s))].add(round(ev.t, 2))
    per_bin = max(1.0, fps * bin_s)
    return Activity(bin_s=bin_s, values=[round(min(1.0, len(s) / per_bin), 2) for s in seen])


def source_scale(info: SourceInfo, meta: FrameMeta) -> tuple[float, float]:
    """Factors from analysis-frame pixels to source display pixels (zones live in the latter)."""
    width, height = output_size(info, max(info.width, info.height))
    return width / meta.width, height / meta.height


def default_pipeline(*, cpu: bool = False) -> Pipeline:
    return Pipeline(
        [ProbeStage(), ReviewCopyStage(cpu=cpu), DetectStage(cpu=cpu), TrackStage(), RidesStage()]
    )

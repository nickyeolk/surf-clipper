"""Concrete pipeline stages, in run order (plan.md; constitution VII).

probe -> detect -> track -> rides. Epochs, zone proposal and refinement are added by later tasks.
Until zone proposal exists (US2), the rides stage needs a zone confirmed with
``surfclip zone SESSION --from-file``.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from surfclip.edits.apply import apply_edits
from surfclip.edits.log import confirmed_zone, read_edits
from surfclip.media.decode import Frame, iter_proxy_frames, output_size
from surfclip.media.export import attach_exports, read_exports
from surfclip.media.probe import probe
from surfclip.pipeline import Pipeline, Stage, StageContext
from surfclip.rides.assemble import assemble
from surfclip.rides.evidence import Evidence, Obs, classify, to_source_pixels
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
    code_version: str = "4"  # 4: bottom-truncated riders; 3: source pixels; 2: stitching

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
        evidence: dict[int, list[Evidence]] = {
            cid: classify(obs, zone, cfg) for cid, obs in chains.items()
        }
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
        return ["rides.detected.json", "rides.json"]


def source_scale(info: SourceInfo, meta: FrameMeta) -> tuple[float, float]:
    """Factors from analysis-frame pixels to source display pixels (zones live in the latter)."""
    width, height = output_size(info, max(info.width, info.height))
    return width / meta.width, height / meta.height


def default_pipeline(*, cpu: bool = False) -> Pipeline:
    return Pipeline([ProbeStage(), DetectStage(cpu=cpu), TrackStage(), RidesStage()])

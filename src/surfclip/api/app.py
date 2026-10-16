"""Local backend for the browser UI (FR-021, FR-025; contracts/http-api.md).

A thin layer over the library: it reads session files, streams the review copy (HTTP Range,
via Starlette's FileResponse) and stores label work. It contains no pipeline logic
(constitution X) and is served on the loopback interface only.
"""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from surfclip.api.jobs import Job, Jobs, Report
from surfclip.config import DEFAULT_CONFIG_PATH, load_config
from surfclip.edits.apply import RIDER_OPS, undone_ids
from surfclip.edits.log import append_edit, confirmed_zone, read_edits
from surfclip.edits.rebuild import rebuild_rides
from surfclip.eval.labels import LabelError, LabelWork, SessionLabels, finalize, work_from_rides
from surfclip.eval.riders import RiderLabelWork, detected_grouping, propose_work
from surfclip.eval.riders import finalize as finalize_riders
from surfclip.media.export import export_reel, export_rides, read_exports, reel_file
from surfclip.media.review import thumbnail
from surfclip.process import (
    SourceNotAllowedError,
    allowed_source,
    list_sources,
    process_session,
    rerun_rides,
)
from surfclip.riders.service import refresh_riders
from surfclip.riders.session import RIDERS_FILE, load_appearance, ride_key
from surfclip.riders.stills import rider_still, still_path
from surfclip.rides.evidence import Obs
from surfclip.store.schemas import (
    EditTarget,
    RiderGroup,
    Riders,
    Rides,
    Session,
    SourceInfo,
    UserEdit,
    Zone,
)
from surfclip.store.session import SessionStore, SourceLocationError, session_id_for
from surfclip.zone.editing import confirm_zone, display_size, keyframe, rider_feet, zone_proposal
from surfclip.zone.geometry import GeometryError


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class SessionSummary(BaseModel):
    session_id: str
    name: str
    source_path: str
    duration_s: float | None
    fps: float | None
    rides: int | None
    short_attempts: int | None
    has_review_copy: bool
    labels_done: int
    labels_total: int
    labels_final: bool
    exported: int
    analysed: bool  # people detected and tracked
    zone_confirmed: bool
    zone_checked: bool  # confirmed by the user, not only the automatic proposal
    job: Job | None  # running analysis or re-run


RideOp = Literal["trim", "split", "merge", "delete", "add", "undo"]


class EditRequest(BaseModel):
    op: RideOp
    target: EditTarget = EditTarget()
    payload: dict[str, float | int] = {}


class ExportRequest(BaseModel):
    rides: list[str] | None = None  # default: every ride (only new or changed ones re-encode)
    reel: bool = False  # also join the clips into one video (clips/reel.mp4)
    rider: str | None = None  # only this rider's rides (name or rider id); reel_<rider>.mp4


RiderOp = Literal["rider_name", "rider_same_as", "rider_mixed", "rider_ignore", "ride_rider"]


class RiderEditRequest(BaseModel):
    """Group ops name a group by ``rider_id`` (and ``other_rider_id`` for same-as); ride ops
    name a ride by ``ride_id``. The server records the rides' spans (groups change on regroup)."""

    op: RiderOp
    rider_id: str | None = None
    other_rider_id: str | None = None
    ride_id: str | None = None
    same_as_ride_id: str | None = None
    to_rider_id: str | None = None  # move ride_id to this rider
    name: str | None = None
    not_name: str | None = None
    ignore: bool = True


class AddSessionRequest(BaseModel):
    source_path: str
    min_length_s: float | None = None


class RerunRequest(BaseModel):
    min_length_s: float


class SourceVideo(BaseModel):
    path: str
    name: str
    size_bytes: int
    session_id: str | None  # already added


def rider_labels(riders: Riders) -> dict[str, str]:
    """Display name per rider id: the user's name, else "Rider N" (largest group first)."""
    return {g.rider_id: g.name or f"Rider {k}" for k, g in enumerate(riders.riders, start=1)}


def rider_ride_ids(riders: Riders, rider: str) -> set[str]:
    """Ride ids of a rider given by id, user name or display name."""
    labels = rider_labels(riders)
    for g in riders.riders:
        if rider in (g.rider_id, g.name, labels[g.rider_id]):
            return set(g.ride_ids)
    raise ApiError(404, "rider_not_found", f"no rider {rider}")


def create_app(
    artifacts: Path,
    labels_dir: Path = Path("labels/rides"),
    web_dist: Path | None = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> FastAPI:
    app = FastAPI(
        title="Surf Session Clipper", docs_url="/api/docs", openapi_url="/api/openapi.json"
    )

    jobs = Jobs()  # clip export (NVENC)
    work_jobs = Jobs()  # analysis and re-runs (CUDA), one at a time

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, exc.status)

    def folder(session_id: str) -> Path:
        path = artifacts / session_id
        if not session_id.isalnum() or not (path / "session.json").exists():
            raise ApiError(404, "session_not_found", f"no session {session_id}")
        return path

    def read(path: Path, model: type[Any]) -> Any:
        if not path.exists():
            raise ApiError(404, "not_ready", f"{path.name} does not exist yet: run the pipeline")
        return model.model_validate_json(path.read_text(encoding="utf-8"))

    def session_of(sid: str) -> Session:
        return read(folder(sid) / "session.json", Session)

    def work_paths(session: Session) -> tuple[Path, Path]:
        stem = Path(session.source_path).stem
        return labels_dir / f"{stem}.work.json", labels_dir / f"{stem}.json"

    def load_work(sid: str) -> LabelWork:
        session = session_of(sid)
        work_file, final_file = work_paths(session)
        if work_file.exists():
            return LabelWork.model_validate_json(work_file.read_text(encoding="utf-8"))
        rides: Rides = read(folder(sid) / "rides.json", Rides)
        work = work_from_rides(rides, Path(session.source_path).name)
        work.finalized = final_file.exists()
        return work

    def save_work(sid: str, work: LabelWork) -> None:
        work_file, _ = work_paths(session_of(sid))
        work_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = work_file.with_suffix(".tmp")
        tmp.write_text(work.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(work_file)

    @app.get("/api/sessions")
    def list_sessions() -> list[SessionSummary]:
        out: list[SessionSummary] = []
        for record in sorted(artifacts.glob("*/session.json")):
            s = Session.model_validate_json(record.read_text(encoding="utf-8"))
            root = record.parent
            info = (
                SourceInfo.model_validate_json((root / "probe.json").read_text(encoding="utf-8"))
                if (root / "probe.json").exists()
                else None
            )
            rides = (
                Rides.model_validate_json((root / "rides.json").read_text(encoding="utf-8"))
                if (root / "rides.json").exists()
                else None
            )
            work_file, final_file = work_paths(s)
            work = (
                LabelWork.model_validate_json(work_file.read_text(encoding="utf-8"))
                if work_file.exists()
                else None
            )
            total = (
                len(work.items)
                if work
                else (len(rides.rides) + len(rides.short_attempts) if rides else 0)
            )
            out.append(
                SessionSummary(
                    session_id=s.session_id,
                    name=Path(s.source_path).name,
                    source_path=s.source_path,
                    duration_s=info.duration_s if info else None,
                    fps=info.avg_fps if info else None,
                    rides=len(rides.rides) if rides else None,
                    short_attempts=len(rides.short_attempts) if rides else None,
                    has_review_copy=(root / "review.mp4").exists(),
                    labels_done=total - work.remaining if work else 0,
                    labels_total=total,
                    labels_final=final_file.exists(),
                    exported=sum(1 for r in rides.rides if r.export) if rides else 0,
                    analysed="track" in s.stages and s.stages["track"].status == "done",
                    zone_confirmed=(zone := confirmed_zone(read_edits(SessionStore(root, s))))
                    is not None,
                    zone_checked=zone is not None and zone.origin == "user",
                    job=work_jobs.active(s.session_id, "analyse")
                    or work_jobs.active(s.session_id, "rerun"),
                )
            )
        return out

    def source_dirs() -> list[str]:
        return load_config(config_path).server.source_dirs

    @app.get("/api/sources")
    def get_sources() -> list[SourceVideo]:
        """Videos in the configured source folders, and whether each is a session already."""
        out: list[SourceVideo] = []
        for p in list_sources(source_dirs()):
            sid = session_id_for(p)
            out.append(
                SourceVideo(
                    path=str(p),
                    name=p.name,
                    size_bytes=p.stat().st_size,
                    session_id=sid if (artifacts / sid / "session.json").exists() else None,
                )
            )
        return out

    @app.post("/api/sessions")
    def add_session(req: AddSessionRequest) -> dict[str, Any]:
        """Add a video and start analysing it (or return the running job)."""
        try:
            source = allowed_source(Path(req.source_path), source_dirs())
            store = SessionStore.open(source, artifacts)
        except (SourceNotAllowedError, SourceLocationError) as exc:
            raise ApiError(400, "source_not_allowed", str(exc)) from exc
        sid = store.session.session_id
        if req.min_length_s is not None:
            if req.min_length_s <= 0:
                raise ApiError(400, "invalid_setting", "minimum ride length must be positive")
            store.session.config_overrides["rides.min_length_s"] = req.min_length_s
            store.save()
        job = work_jobs.active(sid, "analyse") or work_jobs.submit(
            "analyse", sid, lambda report: process_session(store, config_path, report)
        )
        return {"session_id": sid, "job": job.model_dump(mode="json")}

    @app.post("/api/sessions/{sid}/rerun")
    def rerun(sid: str, req: RerunRequest) -> Job:
        """Re-run ride finding with new settings; detection is cached and edits are kept."""
        store = store_of(sid)
        if req.min_length_s <= 0:
            raise ApiError(400, "invalid_setting", "minimum ride length must be positive")
        if confirmed_zone(read_edits(store)) is None:
            raise ApiError(409, "zone_not_confirmed", "set the wave zone first")
        running = work_jobs.active(sid, "rerun") or work_jobs.active(sid, "analyse")
        if running is not None:
            return running
        overrides: dict[str, object] = {"rides.min_length_s": req.min_length_s}
        return work_jobs.submit(
            "rerun", sid, lambda report: rerun_rides(store, config_path, overrides, report)
        )

    @app.get("/api/sessions/{sid}")
    def get_session(sid: str) -> dict[str, Any]:
        zone = confirmed_zone(read_edits(store_of(sid)))
        return {
            "session": session_of(sid).model_dump(mode="json"),
            "zone_origin": zone.origin if zone else None,
            "probe": read(folder(sid) / "probe.json", SourceInfo).model_dump(mode="json"),
        }

    @app.get("/api/sessions/{sid}/rides")
    def get_rides(sid: str, rider: str | None = None) -> dict[str, Any]:
        """Rides; each with its rider (when grouped). ``rider``: only that rider's rides."""
        rides: Rides = read(folder(sid) / "rides.json", Rides)
        out = rides.model_dump(mode="json")
        riders_file = folder(sid) / "riders.json"
        if not riders_file.exists():
            if rider is not None:
                raise ApiError(404, "not_ready", "riders are not grouped yet")
            return out
        riders = Riders.model_validate_json(riders_file.read_text(encoding="utf-8"))
        label = rider_labels(riders)
        conf = {a.ride_id: a for a in riders.assignments}
        keep = rider_ride_ids(riders, rider) if rider is not None else None
        rows: list[dict[str, Any]] = []
        for r in out["rides"]:
            a = conf.get(r["ride_id"])
            r["rider"] = label.get(a.rider_id) if a and a.rider_id else None
            r["rider_id"] = a.rider_id if a else None
            r["rider_confidence"] = a.confidence if a else None
            r["rider_confirmed"] = a.confirmed if a else False
            if keep is None or r["ride_id"] in keep:
                rows.append(r)
        out["rides"] = rows
        return out

    @app.get("/api/sessions/{sid}/activity")
    def get_activity(sid: str) -> dict[str, Any]:
        path = folder(sid) / "activity.json"
        if not path.exists():
            raise ApiError(404, "not_ready", "activity.json does not exist yet: run the pipeline")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/api/sessions/{sid}/labels")
    def get_labels(sid: str) -> LabelWork:
        return load_work(sid)

    @app.put("/api/sessions/{sid}/labels")
    def put_labels(sid: str, work: LabelWork) -> LabelWork:
        work.finalized = False
        save_work(sid, work)
        return work

    @app.post("/api/sessions/{sid}/labels/finalize")
    def finalize_labels(sid: str) -> dict[str, Any]:
        work = load_work(sid)
        try:
            labels = finalize(work)
        except LabelError as exc:
            raise ApiError(409, "labels_incomplete", str(exc)) from exc
        _, final_file = work_paths(session_of(sid))
        final_file.parent.mkdir(parents=True, exist_ok=True)
        final_file.write_text(labels.model_dump_json(indent=2), encoding="utf-8")
        work.finalized = True
        save_work(sid, work)
        return {"rides": len(labels.rides), "path": str(final_file)}

    def store_of(sid: str) -> SessionStore:
        return SessionStore(folder(sid), session_of(sid))

    # ---- rider labels (002 evaluation; never change rides or rider edits) --------------------
    rider_labels_dir = labels_dir.parent / "riders"
    obs_cache: dict[tuple[str, int], list[Obs]] = {}

    def rider_label_paths(session: Session) -> tuple[Path, Path]:
        stem = Path(session.source_path).stem
        return rider_labels_dir / f"{stem}.work.json", rider_labels_dir / f"{stem}.json"

    @app.get("/api/sessions/{sid}/rider-labels")
    def get_rider_labels(sid: str) -> RiderLabelWork:
        session = session_of(sid)
        work_file, final_file = rider_label_paths(session)
        if work_file.exists():
            return RiderLabelWork.model_validate_json(work_file.read_text(encoding="utf-8"))
        _, ride_labels = work_paths(session)
        if not ride_labels.exists():
            raise ApiError(409, "no_ride_labels", "label the rides of this session first")
        labels = SessionLabels.model_validate_json(ride_labels.read_text(encoding="utf-8"))
        detected, riders = detected_grouping(
            store_of(sid), load_config(config_path, session.config_overrides)
        )
        work = propose_work(labels, detected, riders, Path(session.source_path).name)
        work.finalized = final_file.exists()
        return work

    @app.put("/api/sessions/{sid}/rider-labels")
    def put_rider_labels(sid: str, work: RiderLabelWork) -> RiderLabelWork:
        work_file, _ = rider_label_paths(session_of(sid))
        work_file.parent.mkdir(parents=True, exist_ok=True)
        work.finalized = False
        tmp = work_file.with_suffix(".tmp")
        tmp.write_text(work.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(work_file)
        return work

    @app.post("/api/sessions/{sid}/rider-labels/finalize")
    def finalize_rider_labels(sid: str) -> dict[str, Any]:
        work = get_rider_labels(sid)
        try:
            labels = finalize_riders(work)
        except LabelError as exc:
            raise ApiError(409, "labels_incomplete", str(exc)) from exc
        work_file, final_file = rider_label_paths(session_of(sid))
        final_file.parent.mkdir(parents=True, exist_ok=True)
        final_file.write_text(labels.model_dump_json(indent=2), encoding="utf-8")
        work.finalized = True
        work_file.write_text(work.model_dump_json(indent=2), encoding="utf-8")
        return {"rides": len(labels.rides), "riders": len({r.rider for r in labels.rides})}

    @app.get("/api/sessions/{sid}/media/rider-still.jpg")
    def get_rider_still(sid: str, ride: str, t: float | None = None) -> Response:
        """The ride's rider (current or detected ride) at time t, or mid-ride."""
        from surfclip.stages import session_observations

        store = store_of(sid)
        candidates = [
            r
            for name in ("rides.json", "rides.detected.json")
            if store.path(name).exists()
            for r in store.read_model(name, Rides).rides
            if r.ride_id == ride
        ]
        if not candidates:
            raise ApiError(404, "ride_not_found", f"no ride {ride}")
        r = candidates[0]
        if t is None:  # the ride's sharpest crop, saved by the riders stage
            app = load_appearance(store)
            described = app.rides.get(ride_key(r)) if app else None
            if described is not None and described.best_t is not None:
                cached = still_path(store, r.ride_id, described.best_t)
                if cached.exists():
                    return Response(
                        cached.read_bytes(),
                        media_type="image/jpeg",
                        headers={"Cache-Control": "max-age=3600"},
                    )
        tf = store.path("tracks.parquet")
        key = (sid, tf.stat().st_mtime_ns if tf.exists() else 0)
        if key not in obs_cache:
            obs_cache.clear()  # one session at a time is plenty
            obs_cache[key] = session_observations(store)
        got = rider_still(
            store, r, t if t is not None else (r.start_s + r.end_s) / 2, obs_cache[key]
        )
        if got is None:
            raise ApiError(404, "no_still", f"no tracked rider in ride {ride}")
        return Response(got[0], media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})

    @app.get("/api/sessions/{sid}/keyframe.jpg")
    def get_keyframe(sid: str, t: float = 600.0) -> FileResponse:
        try:
            return FileResponse(keyframe(store_of(sid), t), media_type="image/jpeg")
        except subprocess.CalledProcessError as exc:
            raise ApiError(500, "keyframe_failed", "could not extract a still") from exc

    @app.get("/api/sessions/{sid}/zone")
    def get_zone(sid: str) -> dict[str, Any]:
        store = store_of(sid)
        info: SourceInfo = read(folder(sid) / "probe.json", SourceInfo)
        zone = confirmed_zone(read_edits(store))
        proposal = zone_proposal(store)
        face_file = folder(sid) / "face.json"
        width, height = display_size(info)
        return {
            "zone": zone.model_dump(mode="json") if zone else None,
            "face": json.loads(face_file.read_text(encoding="utf-8"))
            if face_file.exists()
            else None,
            "frame": {"width": width, "height": height, "duration_s": info.duration_s},
            "feet": rider_feet(store),
            "proposal": proposal.model_dump(mode="json") if proposal else None,
        }

    @app.put("/api/sessions/{sid}/zone")
    def put_zone(sid: str, zone: Zone) -> dict[str, Any]:
        try:
            rides = confirm_zone(store_of(sid), zone)
        except GeometryError as exc:
            raise ApiError(400, "invalid_zone", str(exc)) from exc
        face_file = folder(sid) / "face.json"
        return {
            "rides": len(rides.rides),
            "short_attempts": len(rides.short_attempts),
            "face": json.loads(face_file.read_text(encoding="utf-8"))
            if face_file.exists()
            else None,
        }

    @app.get("/api/sessions/{sid}/media/review.mp4")
    def review_video(sid: str) -> FileResponse:
        path = folder(sid) / "review.mp4"
        if not path.exists():
            raise ApiError(404, "not_ready", "no review copy yet: run `surfclip run` once more")
        return FileResponse(path, media_type="video/mp4")

    # ---- review: edits and export -------------------------------------------------------------
    write_lock = threading.Lock()  # rides.json writers: edits and the end of an export

    def check_edit(req: EditRequest, rides: Rides, edits: list[UserEdit]) -> list[str]:
        """Validate a ride edit against the current rides; returns the target ride ids."""
        by_id = {r.ride_id: r for r in rides.rides}
        ids = req.target.ride_ids or ([req.target.ride_id] if req.target.ride_id else [])
        p = req.payload

        def bad(message: str) -> ApiError:
            return ApiError(400, "invalid_edit", message)

        if req.op == "undo":
            target = p.get("edit_id")
            if not isinstance(target, int) or not 1 <= target <= len(edits):
                raise bad("undo needs the edit_id of an earlier edit")
            if edits[target - 1].op == "confirm_zone":
                raise bad("zone confirmations are changed in the zone editor, not undone")
            return []
        if req.op == "add":
            if not ("start_s" in p and "end_s" in p and p["end_s"] - p["start_s"] >= 0.5):
                raise bad("add needs start_s < end_s (at least 0.5 s)")
            return []
        if req.op == "merge" and len(ids) < 2:
            raise bad("merge needs at least two ride_ids")
        if req.op != "merge" and len(ids) != 1:
            raise bad(f"{req.op} needs exactly one ride_id")
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise ApiError(404, "ride_not_found", f"no ride {', '.join(missing)}")
        r = by_id[ids[0]]
        if req.op == "trim":
            start, end = p.get("start_s", r.start_s), p.get("end_s", r.end_s)
            if end - start < 0.5:
                raise bad("a trimmed ride must keep at least 0.5 s")
        if req.op == "split" and not ("at_s" in p and r.start_s < p["at_s"] < r.end_s):
            raise bad("split needs at_s inside the ride")
        return ids

    @app.get("/api/sessions/{sid}/edits")
    def get_edits(sid: str) -> dict[str, Any]:
        edits = read_edits(store_of(sid))
        return edits.model_dump(mode="json")

    @app.post("/api/sessions/{sid}/edits")
    def post_edit(sid: str, req: EditRequest) -> dict[str, Any]:
        store = store_of(sid)
        if not store.path("rides.detected.json").exists():
            raise ApiError(404, "not_ready", "no detected rides yet: run the pipeline")
        with write_lock:
            rides: Rides = read(folder(sid) / "rides.json", Rides)
            ids = check_edit(req, rides, read_edits(store).edits)
            payload: dict[str, object] = dict(req.payload)
            if ids:  # where each target ride was, to re-attach the edit after a re-run
                by_id = {r.ride_id: r for r in rides.rides}
                payload["spans"] = {i: [by_id[i].start_s, by_id[i].end_s] for i in ids}
            edit = append_edit(store, req.op, req.target, payload)
            rides = rebuild_rides(store)
            if store.path(RIDERS_FILE).exists():  # riders follow the rides (and rider undos)
                refresh_riders(store, load_config(config_path, store.session.config_overrides))
        return {"edit": edit.model_dump(mode="json"), "rides": rides.model_dump(mode="json")}

    # ---- riders (002) -------------------------------------------------------------------------
    @app.get("/api/sessions/{sid}/riders")
    def get_riders(sid: str) -> dict[str, Any]:
        riders: Riders = read(folder(sid) / RIDERS_FILE, Riders)
        out = riders.model_dump(mode="json")
        labels = rider_labels(riders)
        for g in out["riders"]:
            g["label"] = labels[g["rider_id"]]
        return out

    @app.post("/api/sessions/{sid}/rider-edits")
    def post_rider_edit(sid: str, req: RiderEditRequest) -> dict[str, Any]:
        store = store_of(sid)
        with write_lock:
            riders: Riders = read(folder(sid) / RIDERS_FILE, Riders)
            rides: Rides = read(folder(sid) / "rides.json", Rides)
            by_ride = {r.ride_id: r for r in rides.rides}
            groups = {g.rider_id: g for g in riders.riders}

            def spans_of(ids: list[str]) -> dict[str, list[float]]:
                return {i: [by_ride[i].start_s, by_ride[i].end_s] for i in ids if i in by_ride}

            def group(rider_id: str | None) -> RiderGroup:
                if rider_id is None or rider_id not in groups:
                    raise ApiError(404, "rider_not_found", f"no rider {rider_id}")
                return groups[rider_id]

            def ride_ref(ride_id: str | None) -> list[object]:
                if ride_id is None or ride_id not in by_ride:
                    raise ApiError(404, "ride_not_found", f"no ride {ride_id}")
                r = by_ride[ride_id]
                return [r.ride_id, r.start_s, r.end_s]

            payload: dict[str, object]
            if req.op == "rider_name":
                g = group(req.rider_id)
                if not (req.name or "").strip():
                    raise ApiError(400, "invalid_edit", "a name is needed")
                seen = [g.example_ride_id or "", *(s.ride_id for s in g.stills)]
                payload = {"name": req.name.strip() if req.name else "",
                           "rides": spans_of(g.ride_ids), "examples": spans_of(seen)}  # fmt: skip
            elif req.op == "rider_same_as":
                g, other = group(req.rider_id), group(req.other_rider_id)
                if g.rider_id == other.rider_id:
                    raise ApiError(400, "invalid_edit", "pick another rider")
                payload = {"rides": spans_of(g.ride_ids), "other": spans_of(other.ride_ids)}
            elif req.op == "rider_mixed":
                g = group(req.rider_id)
                if len(g.ride_ids) < 2:
                    raise ApiError(400, "invalid_edit", "a rider with one ride cannot be split")
                payload = {"rides": spans_of(g.ride_ids)}
            elif req.op == "rider_ignore":
                payload = {"rides": spans_of(group(req.rider_id).ride_ids), "ignore": req.ignore}
            else:  # ride_rider
                payload = {"ride": ride_ref(req.ride_id)}
                if req.name:
                    payload["name"] = req.name.strip()
                same_as = req.same_as_ride_id
                if req.to_rider_id:  # move to another rider: join its example ride
                    target = group(req.to_rider_id)
                    same_as = next((r for r in target.ride_ids if r != req.ride_id), None)
                    if target.example_ride_id and target.example_ride_id != req.ride_id:
                        same_as = target.example_ride_id
                if same_as:
                    payload["same_as_ride"] = ride_ref(same_as)
                if req.not_name:
                    payload["not_name"] = req.not_name
                if len(payload) == 1:
                    raise ApiError(400, "invalid_edit", "say who rode it (name, same as or not)")
                if req.to_rider_id or req.name:  # leaving its card: apart from that card
                    home = next((g for g in riders.riders if req.ride_id in g.ride_ids), None)
                    if home is not None and home.rider_id != req.to_rider_id:
                        others = [r for r in home.ride_ids if r != req.ride_id]
                        anchor = (
                            home.example_ride_id
                            if home.example_ride_id and home.example_ride_id != req.ride_id
                            else (others[0] if others else None)
                        )
                        if anchor:
                            payload["away_from"] = ride_ref(anchor)
            edit = append_edit(store, req.op, EditTarget(), payload)
            refresh_riders(store, load_config(config_path, store.session.config_overrides))
        return {"edit": edit.model_dump(mode="json"), "riders": get_riders(sid)["riders"]}

    @app.post("/api/sessions/{sid}/rider-edits/reset")
    def reset_rider_edits(sid: str) -> dict[str, Any]:
        """Start over: undo every rider edit still in effect (the log stays append-only)."""
        store = store_of(sid)
        with write_lock:
            edits = read_edits(store)
            undone = undone_ids(edits)
            active = [e for e in edits.edits if e.op in RIDER_OPS and e.edit_id not in undone]
            for e in reversed(active):
                append_edit(store, "undo", EditTarget(), {"edit_id": e.edit_id})
            if active:
                refresh_riders(store, load_config(config_path, store.session.config_overrides))
        return {"undone": len(active), "riders": get_riders(sid)["riders"]}

    @app.post("/api/sessions/{sid}/export")
    def post_export(sid: str, req: ExportRequest) -> Job:
        store = store_of(sid)
        read(folder(sid) / "rides.json", Rides)
        running = jobs.active(sid, "export")
        if running is not None:
            return running
        cfg = load_config(config_path, store.session.config_overrides)

        def work(report: Report) -> dict[str, object]:
            def progress(i: int, n: int, rid: str) -> None:
                report((i - 1) / max(n, 1), f"encoding {rid} ({i}/{n})")

            ids = req.rides
            if req.rider is not None:
                riders = Riders.model_validate_json(
                    store.path(RIDERS_FILE).read_text(encoding="utf-8")
                )
                ids = sorted(rider_ride_ids(riders, req.rider))
            if req.reel:
                reel = export_reel(
                    store,
                    cfg.export,
                    ride_ids=ids,
                    progress=progress,
                    out_name=reel_file(req.rider),
                )
                with write_lock:
                    rebuild_rides(store)
                return {"reel": str(reel), "folder": str(store.path("clips"))}
            done, skipped = export_rides(store, cfg.export, ride_ids=ids, progress=progress)
            with write_lock:
                rebuild_rides(store)
            return {"exported": done, "up_to_date": skipped, "folder": str(store.path("clips"))}

        return jobs.submit("export", sid, work)

    @app.get("/api/sessions/{sid}/media/reel.mp4")
    def reel_video(sid: str, rider: str | None = None) -> FileResponse:
        path = folder(sid) / reel_file(rider)
        if not path.exists():
            raise ApiError(404, "not_exported", "no reel yet: export one first")
        return FileResponse(path, media_type="video/mp4")

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> Job:
        job = jobs.get(job_id) or work_jobs.get(job_id)
        if job is None:
            raise ApiError(404, "job_not_found", f"no job {job_id}")
        return job

    @app.get("/api/sessions/{sid}/media/clips/{ride_id}.mp4")
    def clip_video(sid: str, ride_id: str) -> FileResponse:
        store = store_of(sid)
        rec = read_exports(store).records.get(ride_id)
        if rec is None or not store.path(rec.path).exists():
            raise ApiError(404, "not_exported", f"ride {ride_id} has no exported clip yet")
        return FileResponse(store.path(rec.path), media_type="video/mp4")

    @app.get("/api/sessions/{sid}/media/thumb.jpg")
    def ride_thumb(sid: str, t: float) -> FileResponse:
        root = folder(sid)
        if not (root / "review.mp4").exists():
            raise ApiError(404, "not_ready", "no review copy yet")
        try:
            path = thumbnail(root / "review.mp4", t, root / "thumbs")
        except subprocess.CalledProcessError as exc:
            raise ApiError(500, "thumb_failed", "could not extract a still") from exc
        return FileResponse(path, media_type="image/jpeg")

    if web_dist is not None and (web_dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
    return app

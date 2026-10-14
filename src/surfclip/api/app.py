"""Local backend for the browser UI (FR-021, FR-025; contracts/http-api.md).

A thin layer over the library: it reads session files, streams the review copy (HTTP Range,
via Starlette's FileResponse) and stores label work. It contains no pipeline logic
(constitution X) and is served on the loopback interface only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from surfclip.eval.labels import LabelError, LabelWork, finalize, work_from_rides
from surfclip.store.schemas import Rides, Session, SourceInfo


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


def create_app(
    artifacts: Path, labels_dir: Path = Path("labels/rides"), web_dist: Path | None = None
) -> FastAPI:
    app = FastAPI(
        title="Surf Session Clipper", docs_url="/api/docs", openapi_url="/api/openapi.json"
    )

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
                )
            )
        return out

    @app.get("/api/sessions/{sid}")
    def get_session(sid: str) -> dict[str, Any]:
        return {
            "session": session_of(sid).model_dump(mode="json"),
            "probe": read(folder(sid) / "probe.json", SourceInfo).model_dump(mode="json"),
        }

    @app.get("/api/sessions/{sid}/rides")
    def get_rides(sid: str) -> dict[str, Any]:
        return read(folder(sid) / "rides.json", Rides).model_dump(mode="json")

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

    @app.get("/api/sessions/{sid}/media/review.mp4")
    def review_video(sid: str) -> FileResponse:
        path = folder(sid) / "review.mp4"
        if not path.exists():
            raise ApiError(404, "not_ready", "no review copy yet: run `surfclip run` once more")
        return FileResponse(path, media_type="video/mp4")

    if web_dist is not None and (web_dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
    return app

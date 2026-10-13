"""Per-session folders under artifacts/, stage records and cache keys (constitution VII).

A session folder is ``<artifacts>/<session_id>/``. Source videos are only ever read: the
store refuses an artifacts root inside the source video's folder (FR-003).
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from surfclip.store.schemas import Session, StageName, StageStatus


class SourceLocationError(ValueError):
    """Raised when outputs would be written next to (or inside) the source footage."""


def session_id_for(source: Path) -> str:
    """Short, stable id from the source's absolute path, size and modification time."""
    st = source.stat()
    ident = f"{source.resolve()}|{st.st_size}|{st.st_mtime_ns}"
    return hashlib.sha256(ident.encode()).hexdigest()[:10]


def cache_key(
    stage: StageName, *, inputs: list[str], config_hashes: list[str], code_version: str
) -> str:
    """Key that changes when a stage's inputs, relevant config, or code version change."""
    payload = "|".join([stage, code_version, *sorted(inputs), *sorted(config_hashes)])
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class SessionStore:
    def __init__(self, root: Path, session: Session) -> None:
        self.root = root
        self.session = session

    @classmethod
    def open(cls, source: Path, artifacts_root: Path) -> SessionStore:
        source = source.resolve()
        artifacts_root = artifacts_root.resolve()
        if artifacts_root.is_relative_to(source.parent):
            raise SourceLocationError(
                f"artifacts root {artifacts_root} is inside the source folder {source.parent}"
            )
        sid = session_id_for(source)
        root = artifacts_root / sid
        root.mkdir(parents=True, exist_ok=True)
        record = root / "session.json"
        if record.exists():
            session = Session.model_validate_json(record.read_text(encoding="utf-8"))
        else:
            st = source.stat()
            session = Session(
                session_id=sid,
                source_path=str(source),
                source_size=st.st_size,
                source_mtime=st.st_mtime,
                created_at=datetime.now(UTC),
            )
        store = cls(root, session)
        store.save()
        return store

    @property
    def source(self) -> Path:
        return Path(self.session.source_path)

    def path(self, name: str) -> Path:
        return self.root / name

    def save(self) -> None:
        _atomic_write_text(self.path("session.json"), self.session.model_dump_json(indent=2))

    def write_model(self, name: str, model: BaseModel) -> Path:
        target = self.path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(target, model.model_dump_json(indent=2))
        return target

    def read_model[M: BaseModel](self, name: str, cls: type[M]) -> M:
        return cls.model_validate_json(self.path(name).read_text(encoding="utf-8"))

    # --- stage records ----------------------------------------------------------------------

    def is_fresh(self, stage: StageName, key: str) -> bool:
        status = self.session.stages.get(stage)
        return (
            status is not None
            and status.status == "done"
            and status.cache_key == key
            and all(self.path(o).exists() for o in status.outputs)
        )

    def mark_running(self, stage: StageName) -> None:
        self.session.stages[stage] = StageStatus(status="running")
        self.save()

    def mark_done(self, stage: StageName, key: str, outputs: list[str]) -> None:
        self.session.stages[stage] = StageStatus(
            status="done", cache_key=key, outputs=outputs, finished_at=datetime.now(UTC)
        )
        self.save()

    def mark_failed(self, stage: StageName, error: str) -> None:
        self.session.stages[stage] = StageStatus(
            status="failed", error=error, finished_at=datetime.now(UTC)
        )
        self.save()

"""Background jobs for the local backend (clip export).

One worker: jobs share the GPU encoder, so they run one at a time in submission order.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "done", "failed"]


class Job(BaseModel):
    job_id: str
    kind: str
    session_id: str
    status: JobStatus = "queued"
    progress: float = 0.0  # 0..1
    message: str = ""
    result: dict[str, object] = Field(default_factory=dict[str, object])
    error: str | None = None


Report = Callable[[float, str], None]


class Jobs:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="surfclip-job")

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy() if job else None

    def active(self, session_id: str, kind: str) -> Job | None:
        with self._lock:
            for job in self._jobs.values():
                if (job.session_id, job.kind) == (session_id, kind) and job.status in (
                    "queued",
                    "running",
                ):
                    return job.model_copy()
        return None

    def submit(
        self, kind: str, session_id: str, work: Callable[[Report], dict[str, object]]
    ) -> Job:
        job = Job(job_id=uuid.uuid4().hex[:12], kind=kind, session_id=session_id)
        with self._lock:
            self._jobs[job.job_id] = job

        def report(progress: float, message: str) -> None:
            with self._lock:
                job.progress, job.message = max(0.0, min(1.0, progress)), message

        def run() -> None:
            with self._lock:
                job.status = "running"
            try:
                result = work(report)
            except Exception as exc:  # reported to the UI, not raised in the worker
                log.exception("job %s (%s) failed", job.job_id, kind)
                with self._lock:
                    job.status, job.error = "failed", str(exc)
                return
            with self._lock:
                job.status, job.progress, job.result = "done", 1.0, result

        self._pool.submit(run)
        return job.model_copy()

"""Stage orchestration with caching (constitution VII, FR-023).

A stage's cache key covers its code version, the config sections it reads, and the cache keys
of the stages it depends on. Changing a ride threshold therefore re-runs only the ride stages,
never detection; changing detection re-runs everything downstream of it. Stages never write
``edits.json`` (constitution VI).
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from surfclip.config import Config
from surfclip.store.schemas import StageName
from surfclip.store.session import SessionStore, cache_key


@dataclass(frozen=True)
class StageContext:
    store: SessionStore
    config: Config


class Stage(ABC):
    name: StageName
    depends_on: tuple[StageName, ...]
    config_sections: tuple[str, ...]
    code_version: str

    @abstractmethod
    def run(self, ctx: StageContext) -> list[str]:
        """Do the work; return output file names relative to the session folder."""

    def extra_inputs(self, store: SessionStore) -> list[str]:
        """Inputs beyond upstream stages and config, e.g. a confirmed zone (part of the key)."""
        return []


@dataclass
class RunReport:
    ran: list[StageName] = field(default_factory=list[StageName])
    cache_hits: list[StageName] = field(default_factory=list[StageName])
    seconds: dict[StageName, float] = field(default_factory=dict[StageName, float])


def _session_logger(store: SessionStore) -> logging.Logger:
    logger = logging.getLogger(f"surfclip.session.{store.session.session_id}")
    log_path = str(store.path("pipeline.log"))
    if not any(getattr(h, "baseFilename", None) == log_path for h in logger.handlers):
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


class Pipeline:
    def __init__(self, stages: list[Stage]) -> None:
        seen: set[StageName] = set()
        for stage in stages:
            missing = [d for d in stage.depends_on if d not in seen]
            if missing:
                raise ValueError(
                    f"stage {stage.name} depends on {missing}, which must run before it"
                )
            seen.add(stage.name)
        self.stages = stages

    def run(
        self, store: SessionStore, config: Config, *, until: StageName | None = None
    ) -> RunReport:
        log = _session_logger(store)
        report = RunReport()
        keys: dict[StageName, str] = {}
        for stage in self.stages:
            key = cache_key(
                stage.name,
                inputs=[f"{d}:{keys[d]}" for d in stage.depends_on]
                + [store.session.source_path, *stage.extra_inputs(store)],
                config_hashes=[config.section_hash(s) for s in stage.config_sections],
                code_version=stage.code_version,
            )
            keys[stage.name] = key
            if store.is_fresh(stage.name, key):
                report.cache_hits.append(stage.name)
                log.info("%s cache hit (%s)", stage.name, key)
            else:
                log.info("%s running (%s)", stage.name, key)
                store.mark_running(stage.name)
                started = time.perf_counter()
                try:
                    outputs = stage.run(StageContext(store, config))
                except Exception as exc:
                    store.mark_failed(stage.name, f"{type(exc).__name__}: {exc}")
                    log.error("%s failed: %s", stage.name, exc)
                    raise
                store.mark_done(stage.name, key, outputs)
                report.seconds[stage.name] = time.perf_counter() - started
                report.ran.append(stage.name)
                log.info("%s done in %.1fs", stage.name, report.seconds[stage.name])
            if stage.name == until:
                break
        return report

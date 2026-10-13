"""Concrete pipeline stages, in run order. Later tasks append detection, tracking, etc."""

from __future__ import annotations

from dataclasses import dataclass

from surfclip.media.probe import probe
from surfclip.pipeline import Pipeline, Stage, StageContext
from surfclip.store.schemas import StageName


@dataclass
class ProbeStage(Stage):
    name: StageName = "probe"
    depends_on: tuple[StageName, ...] = ()
    config_sections: tuple[str, ...] = ()
    code_version: str = "1"

    def run(self, ctx: StageContext) -> list[str]:
        ctx.store.write_model("probe.json", probe(ctx.store.source))
        return ["probe.json"]


def default_pipeline() -> Pipeline:
    return Pipeline([ProbeStage()])

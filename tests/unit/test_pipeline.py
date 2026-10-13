from dataclasses import dataclass, field
from pathlib import Path

import pytest

from surfclip.config import load_config
from surfclip.pipeline import Pipeline, Stage, StageContext
from surfclip.store.schemas import StageName
from surfclip.store.session import SessionStore


@dataclass
class FakeStage(Stage):
    name: StageName
    depends_on: tuple[StageName, ...] = ()
    config_sections: tuple[str, ...] = ()
    code_version: str = "1"
    runs: int = 0
    fail: bool = False
    outputs: list[str] = field(default_factory=list[str])

    def run(self, ctx: StageContext) -> list[str]:
        self.runs += 1
        if self.fail:
            raise RuntimeError("boom")
        out = f"{self.name}.out"
        ctx.store.path(out).write_text(str(self.runs))
        return [out]


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    src = tmp_path / "src" / "v.mp4"
    src.parent.mkdir()
    src.write_bytes(b"x")
    return SessionStore.open(src, tmp_path / "artifacts")


def _stages() -> dict[StageName, FakeStage]:
    return {
        "probe": FakeStage("probe"),
        "detect": FakeStage("detect", depends_on=("probe",), config_sections=("detect",)),
        "rides": FakeStage("rides", depends_on=("detect",), config_sections=("rides",)),
    }


def test_second_run_is_all_cache_hits(store: SessionStore) -> None:
    stages = _stages()
    cfg = load_config()
    Pipeline(list(stages.values())).run(store, cfg)
    report = Pipeline(list(stages.values())).run(store, cfg)
    assert [s.runs for s in stages.values()] == [1, 1, 1]
    assert report.cache_hits == ["probe", "detect", "rides"]


def test_rides_config_change_reruns_only_rides(store: SessionStore) -> None:
    stages = _stages()
    Pipeline(list(stages.values())).run(store, load_config())
    report = Pipeline(list(stages.values())).run(
        store, load_config(overrides={"rides.min_length_s": 15})
    )
    assert [s.runs for s in stages.values()] == [1, 1, 2]
    assert report.ran == ["rides"]


def test_upstream_rerun_invalidates_downstream(store: SessionStore) -> None:
    stages = _stages()
    Pipeline(list(stages.values())).run(store, load_config())
    stages["detect"].code_version = "2"
    Pipeline(list(stages.values())).run(store, load_config())
    assert [s.runs for s in stages.values()] == [1, 2, 2]


def test_run_until_stops_early(store: SessionStore) -> None:
    stages = _stages()
    Pipeline(list(stages.values())).run(store, load_config(), until="detect")
    assert [s.runs for s in stages.values()] == [1, 1, 0]


def test_failure_is_recorded_and_raised(store: SessionStore) -> None:
    stages = _stages()
    stages["detect"].fail = True
    with pytest.raises(RuntimeError, match="boom"):
        Pipeline(list(stages.values())).run(store, load_config())
    assert store.session.stages["detect"].status == "failed"
    assert "boom" in (store.session.stages["detect"].error or "")
    assert stages["rides"].runs == 0
    assert "detect failed" in store.path("pipeline.log").read_text()


def test_unknown_dependency_is_rejected() -> None:
    with pytest.raises(ValueError, match="before"):
        Pipeline([FakeStage("rides", depends_on=("detect",))])

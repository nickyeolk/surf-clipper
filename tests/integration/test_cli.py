import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from surfclip.cli import app

SAMPLES = Path(os.environ.get("SURFCLIP_SAMPLES", "/mnt/c/Users/likkhian/OneDrive/Media/trifecta"))
ARCHIVE = SAMPLES / "20241004.MP4"

pytestmark = pytest.mark.integration
runner = CliRunner()


@pytest.fixture(scope="module")
def archive() -> Path:
    if not ARCHIVE.exists():
        pytest.skip(f"{ARCHIVE} not available")
    return ARCHIVE


def test_probe_prints_summary(archive: Path) -> None:
    result = runner.invoke(app, ["probe", str(archive)])
    assert result.exit_code == 0, result.output
    assert "h264 1280x720 30.00 fps, 8-bit SDR" in result.output


def test_probe_missing_file_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["probe", str(tmp_path / "nope.mp4")])
    assert result.exit_code == 2


def test_ingest_creates_session_then_hits_cache(archive: Path, tmp_path: Path) -> None:
    args = ["ingest", str(archive), "--artifacts", str(tmp_path), "--min-length", "12", "--json"]
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    out = json.loads(first.stdout)
    folder = Path(out["folder"])
    assert out["ran"] == ["probe"]
    assert (folder / "probe.json").exists()
    session = json.loads((folder / "session.json").read_text())
    assert session["config_overrides"] == {"rides.min_length_s": 12.0}
    second = json.loads(runner.invoke(app, args).stdout)
    assert second["cache_hits"] == ["probe"] and second["ran"] == []


def test_ingest_refuses_artifacts_next_to_source(archive: Path) -> None:
    result = runner.invoke(app, ["ingest", str(archive), "--artifacts", str(archive.parent / "x")])
    assert result.exit_code == 2
    assert not (archive.parent / "x").exists()

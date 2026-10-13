from pathlib import Path

import pytest

from surfclip.store.schemas import Edits
from surfclip.store.session import SessionStore, SourceLocationError, cache_key, session_id_for


@pytest.fixture
def source(tmp_path: Path) -> Path:
    src_dir = tmp_path / "footage"
    src_dir.mkdir()
    video = src_dir / "session.MP4"
    video.write_bytes(b"\x00" * 1024)
    return video


def test_session_id_is_stable_and_depends_on_file_identity(source: Path) -> None:
    first = session_id_for(source)
    assert first == session_id_for(source)
    assert len(first) == 10
    source.write_bytes(b"\x01" * 2048)
    assert session_id_for(source) != first


def test_open_creates_folder_and_session_record(source: Path, tmp_path: Path) -> None:
    store = SessionStore.open(source, tmp_path / "artifacts")
    assert store.root == tmp_path / "artifacts" / session_id_for(source)
    assert (store.root / "session.json").exists()
    reopened = SessionStore.open(source, tmp_path / "artifacts")
    assert reopened.session.created_at == store.session.created_at


def test_artifacts_inside_source_folder_are_refused(source: Path) -> None:
    with pytest.raises(SourceLocationError):
        SessionStore.open(source, source.parent / "artifacts")


def test_writes_are_atomic_and_round_trip(source: Path, tmp_path: Path) -> None:
    store = SessionStore.open(source, tmp_path / "artifacts")
    store.write_model("edits.json", Edits())
    assert store.read_model("edits.json", Edits) == Edits()
    assert not list(store.root.glob("*.tmp"))


def test_stage_lifecycle_and_cache_hit(source: Path, tmp_path: Path) -> None:
    store = SessionStore.open(source, tmp_path / "artifacts")
    key = cache_key("detect", inputs=["proxy:abc"], config_hashes=["h1"], code_version="1")
    assert not store.is_fresh("detect", key)
    store.mark_running("detect")
    store.mark_done("detect", key, outputs=["detections.parquet"])
    assert not store.is_fresh("detect", key), "missing output file must not count as fresh"
    store.path("detections.parquet").write_bytes(b"")
    assert store.is_fresh("detect", key)
    other = cache_key("detect", inputs=["proxy:abc"], config_hashes=["h2"], code_version="1")
    assert not store.is_fresh("detect", other)
    reopened = SessionStore.open(source, tmp_path / "artifacts")
    assert reopened.is_fresh("detect", key)


def test_failed_stage_records_error(source: Path, tmp_path: Path) -> None:
    store = SessionStore.open(source, tmp_path / "artifacts")
    store.mark_failed("probe", "unsupported codec")
    assert store.session.stages["probe"].status == "failed"
    assert store.session.stages["probe"].error == "unsupported codec"

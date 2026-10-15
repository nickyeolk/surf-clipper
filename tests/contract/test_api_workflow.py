"""API contract for the browser-only workflow: sources, adding a session, re-runs, the reel."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import surfclip.api.app as app_module
from surfclip.api.app import create_app
from surfclip.config import DEFAULT_CONFIG_PATH


@pytest.fixture
def env(tmp_path: Path) -> tuple[TestClient, Path, Path]:
    footage = tmp_path / "footage"
    footage.mkdir()
    (footage / "session.MP4").write_bytes(b"\x00" * 2048)
    (footage / "notes.txt").write_text("not a video")
    config = tmp_path / "config.toml"
    text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
    start = text.index("source_dirs = [")
    end = text.index("]", start) + 1
    config.write_text(text[:start] + f'source_dirs = ["{footage.as_posix()}"]' + text[end:])
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    client = TestClient(create_app(artifacts, labels_dir=tmp_path / "labels", config_path=config))
    return client, footage, artifacts


def wait(client: TestClient, job_id: str) -> dict[str, object]:
    for _ in range(200):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_sources_lists_videos_only(env: tuple[TestClient, Path, Path]) -> None:
    client, _, _ = env
    (src,) = client.get("/api/sources").json()
    assert (src["name"], src["size_bytes"], src["session_id"]) == ("session.MP4", 2048, None)


def test_add_session_starts_analysis(
    env: tuple[TestClient, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, footage, artifacts = env
    seen: list[str] = []

    def fake_process(store, config_path, report):  # type: ignore[no-untyped-def]
        seen.append(store.session.session_id)
        report(0.5, "finding people")
        return {"next": "zone"}

    monkeypatch.setattr(app_module, "process_session", fake_process)
    r = client.post(
        "/api/sessions", json={"source_path": str(footage / "session.MP4"), "min_length_s": 12}
    )
    assert r.status_code == 200
    body = r.json()
    job = wait(client, body["job"]["job_id"])
    assert job["status"] == "done" and job["result"] == {"next": "zone"}
    assert seen == [body["session_id"]]
    session = (artifacts / body["session_id"] / "session.json").read_text()
    assert '"rides.min_length_s":12' in session.replace(" ", "")
    assert client.get("/api/sources").json()[0]["session_id"] == body["session_id"]
    (s,) = client.get("/api/sessions").json()
    assert not s["analysed"] and not s["zone_confirmed"]


@pytest.mark.parametrize(
    ("path", "code"),
    [("/etc/passwd", "source_not_allowed"), ("{footage}/notes.txt", "source_not_allowed")],
)
def test_add_session_outside_footage_is_refused(
    env: tuple[TestClient, Path, Path], path: str, code: str
) -> None:
    client, footage, _ = env
    r = client.post("/api/sessions", json={"source_path": path.format(footage=footage)})
    assert r.status_code == 400 and r.json()["error"]["code"] == code


def test_rerun_needs_a_zone_and_a_valid_length(
    env: tuple[TestClient, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, footage, _ = env
    monkeypatch.setattr(app_module, "process_session", lambda *_: {"next": "zone"})
    sid = client.post("/api/sessions", json={"source_path": str(footage / "session.MP4")}).json()[
        "session_id"
    ]
    bad = client.post(f"/api/sessions/{sid}/rerun", json={"min_length_s": 0})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_setting"
    no_zone = client.post(f"/api/sessions/{sid}/rerun", json={"min_length_s": 15})
    assert no_zone.status_code == 409 and no_zone.json()["error"]["code"] == "zone_not_confirmed"


def test_reel_not_exported_yet(
    env: tuple[TestClient, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, footage, _ = env
    monkeypatch.setattr(app_module, "process_session", lambda *_: {"next": "zone"})
    sid = client.post("/api/sessions", json={"source_path": str(footage / "session.MP4")}).json()[
        "session_id"
    ]
    r = client.get(f"/api/sessions/{sid}/media/reel.mp4")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_exported"

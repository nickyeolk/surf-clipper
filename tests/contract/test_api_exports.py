"""003 T009: health, model download and shutdown."""

import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import surfclip.health as health_module
from surfclip.api.app import create_app


@pytest.fixture
def stopped() -> threading.Event:
    return threading.Event()


@pytest.fixture
def client(tmp_path: Path, stopped: threading.Event, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(health_module, "gpu", lambda: True)
    monkeypatch.setattr(health_module, "nvenc", lambda: False)
    monkeypatch.setenv("TORCH_HOME", str(tmp_path / "torch"))
    (tmp_path / "artifacts").mkdir()
    return TestClient(create_app(tmp_path / "artifacts", on_shutdown=stopped.set))


def test_health_reports_gpu_encoder_and_models(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["ok"] is True and body["gpu"] is True
    assert body["encoder"] == "cpu"  # NVENC test failed
    assert set(body["models"]) == {"detector", "embedder", "pose"}
    assert body["models"]["embedder"] is False  # empty torch hub


def test_shutdown_calls_the_exit_hook(client: TestClient, stopped: threading.Event) -> None:
    assert client.post("/api/shutdown").json() == {"stopping": True}
    assert stopped.wait(2)


def test_models_download_runs_once(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    gate = threading.Event()
    import surfclip.detect.detector as detector

    monkeypatch.setattr(detector, "download_model", lambda cfg: gate.wait(5) and Path("m.pt"))
    import surfclip.riders.describe as describe

    monkeypatch.setattr(describe, "download_embedder", lambda: Path("hub"))
    first = client.post("/api/models/download")
    assert first.status_code == 200
    assert client.post("/api/models/download").status_code == 409
    gate.set()


# ---- stills and the exports listing (T018, T020) ---------------------------------------------

S = "/api/sessions/abc123"


@pytest.fixture
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Path]:
    import json
    from datetime import UTC, datetime

    from surfclip.store.schemas import Session
    from tests.contract.test_api_labels import PROBE
    from tests.unit.test_labels import EXAMPLE

    root = tmp_path / "artifacts" / "abc123"
    (root / "clips").mkdir(parents=True)
    session = Session(session_id="abc123", source_path="/videos/s.MP4", source_size=1,
                      source_mtime=0, created_at=datetime(2026, 10, 16, tzinfo=UTC))  # fmt: skip
    (root / "session.json").write_text(session.model_dump_json())
    (root / "probe.json").write_text(json.dumps(PROBE))
    rides = json.loads(json.dumps(EXAMPLE))
    rides["rides"][0]["export"] = {
        "path": "clips/r004512.mp4", "cache_key": "k", "exported_at": "2026-10-16T00:00:00Z",
        "span": [149.4, 173.4],
    }  # fmt: skip
    (root / "rides.json").write_text(json.dumps(rides))
    (root / "clips" / "r004512.mp4").write_bytes(b"\0")
    return TestClient(create_app(root.parent)), root


def _fake_save(store: object, cfg: object, t_s: float) -> tuple[object, bool]:
    from datetime import UTC, datetime
    from pathlib import Path as P

    from surfclip.media.stills import STILL_DIR, StillError, read_stills
    from surfclip.store.schemas import Still

    if t_s > 600:
        raise StillError("outside")
    s = store  # a SessionStore
    stills = read_stills(s)  # type: ignore[arg-type]
    name = "r004512_f004512.jpg"
    if any(x.name == name for x in stills.stills):
        return stills.stills[0], False
    P(s.path(STILL_DIR)).mkdir(parents=True, exist_ok=True)  # type: ignore[attr-defined]
    s.path(f"{STILL_DIR}/{name}").write_bytes(b"\xff\xd8")  # type: ignore[attr-defined]
    still = Still(name=name, path=f"{STILL_DIR}/{name}", t_s=150.4, frame=4512,
                  ride_id="r004512", rider=None, width=1280, height=720,
                  saved_at=datetime(2026, 10, 16, tzinfo=UTC))  # fmt: skip
    stills.stills.append(still)
    s.write_model("clips/stills.json", stills)  # type: ignore[attr-defined]
    return still, True


def test_stills_round_trip(
    session: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import surfclip.api.app as app_module

    client, _ = session
    monkeypatch.setattr(app_module, "save_still", _fake_save)
    first = client.post(f"{S}/stills", json={"t_s": 150.41})
    assert first.status_code == 201
    assert first.json()["url"] == f"{S}/media/stills/r004512_f004512.jpg"
    assert client.post(f"{S}/stills", json={"t_s": 150.41}).status_code == 200
    assert client.post(f"{S}/stills", json={"t_s": 9999}).status_code == 400
    img = client.get(f"{S}/media/stills/r004512_f004512.jpg?download=1")
    assert img.status_code == 200 and "attachment" in img.headers["content-disposition"]
    listing = client.get(f"{S}/exports").json()
    assert [s["name"] for s in listing["stills"]] == ["r004512_f004512.jpg"]
    assert client.delete(f"{S}/stills/r004512_f004512.jpg").status_code == 204
    assert client.delete(f"{S}/stills/r004512_f004512.jpg").status_code == 404
    assert client.delete(f"{S}/stills/..%2Frides.json").status_code in (400, 404)


def test_exports_without_riders_lists_unassigned_clips(session: tuple[TestClient, Path]) -> None:
    client, _ = session
    body = client.get(f"{S}/exports").json()
    assert body["fps"] == 30.0 and body["compilations"] == [] and body["riders"] == []
    assert body["unassigned"] == [
        {"ride_id": "r004512", "url": f"{S}/media/clips/r004512.mp4", "clip_start_s": 149.4,
         "duration_s": 24.0}
    ]  # fmt: skip

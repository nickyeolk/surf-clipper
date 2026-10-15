"""T052: API contract for review edits, export jobs and clip media."""

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import surfclip.api.app as app_module
from surfclip.api.app import create_app
from tests.contract.test_api_labels import PROBE
from tests.unit.test_labels import EXAMPLE

S = "/api/sessions/abc123"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    from datetime import UTC, datetime

    from surfclip.store.schemas import Session

    root = tmp_path / "artifacts" / "abc123"
    root.mkdir(parents=True)
    session = Session(
        session_id="abc123",
        source_path="/videos/s.MP4",
        source_size=1,
        source_mtime=0,
        created_at=datetime(2026, 10, 15, tzinfo=UTC),
    )
    (root / "session.json").write_text(session.model_dump_json())
    (root / "probe.json").write_text(json.dumps(PROBE))
    (root / "rides.detected.json").write_text(json.dumps(EXAMPLE))
    (root / "rides.json").write_text(json.dumps(EXAMPLE))
    return root


@pytest.fixture
def client(root: Path) -> TestClient:
    return TestClient(create_app(root.parent, labels_dir=root.parent.parent / "labels"))


def test_trim_records_span_and_updates_rides(client: TestClient, root: Path) -> None:
    r = client.post(
        f"{S}/edits",
        json={"op": "trim", "target": {"ride_id": "r004512"}, "payload": {"end_s": 175}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["edit"]["payload"]["spans"] == {"r004512": [150.4, 171.9]}
    (ride,) = body["rides"]["rides"]
    assert ride["end_s"] == 175 and ride["flags"]["user_edited"]
    assert json.loads((root / "rides.json").read_text())["rides"][0]["end_s"] == 175
    assert json.loads((root / "rides.detected.json").read_text()) == EXAMPLE
    assert [e["op"] for e in client.get(f"{S}/edits").json()["edits"]] == ["trim"]


def test_add_then_undo(client: TestClient) -> None:
    r = client.post(f"{S}/edits", json={"op": "add", "payload": {"start_s": 200.7, "end_s": 205.1}})
    assert [x["ride_id"] for x in r.json()["rides"]["rides"]] == ["r004512", "u0001"]
    r = client.post(f"{S}/edits", json={"op": "undo", "payload": {"edit_id": 1}})
    assert [x["ride_id"] for x in r.json()["rides"]["rides"]] == ["r004512"]


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"op": "trim", "target": {"ride_id": "r004512"}, "payload": {"end_s": 150.5}}, 400),
        ({"op": "split", "target": {"ride_id": "r004512"}, "payload": {"at_s": 300}}, 400),
        ({"op": "merge", "target": {"ride_ids": ["r004512"]}}, 400),
        ({"op": "delete", "target": {"ride_id": "r000001"}}, 404),
        ({"op": "undo", "payload": {"edit_id": 5}}, 400),
        ({"op": "confirm_zone", "target": {"epoch_id": 0}}, 422),
    ],
)
def test_invalid_edits_are_rejected(
    client: TestClient, root: Path, body: object, code: int
) -> None:
    r = client.post(f"{S}/edits", json=body)
    assert r.status_code == code
    if code != 422:
        assert "error" in r.json()
    assert not (root / "edits.json").exists()


def test_export_job_runs_and_reports(
    client: TestClient, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str] | None] = []

    def fake_export(store, cfg, *, ride_ids=None, cpu=False, progress=None):  # type: ignore[no-untyped-def]
        calls.append(ride_ids)
        if progress:
            progress(1, 1, "r004512")
        return ["r004512"], []

    monkeypatch.setattr(app_module, "export_rides", fake_export)
    job = client.post(f"{S}/export", json={"rides": ["r004512"]}).json()
    for _ in range(100):
        job = client.get(f"/api/jobs/{job['job_id']}").json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.02)
    assert job["status"] == "done", job
    assert job["result"]["exported"] == ["r004512"]
    assert calls == [["r004512"]]


def test_unknown_job_and_missing_clip(client: TestClient) -> None:
    assert client.get("/api/jobs/nope").json()["error"]["code"] == "job_not_found"
    r = client.get(f"{S}/media/clips/r004512.mp4")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_exported"


def test_exported_clip_is_served_with_range(client: TestClient, root: Path) -> None:
    (root / "clips").mkdir()
    (root / "clips" / "r004512.mp4").write_bytes(bytes(range(256)) * 4)
    (root / "exports.json").write_text(
        json.dumps(
            {
                "records": {
                    "r004512": {
                        "path": "clips/r004512.mp4",
                        "cache_key": "k",
                        "exported_at": "2026-10-15T00:00:00Z",
                        "span": [149.4, 173.4],
                    }
                }
            }
        )
    )
    r = client.get(f"{S}/media/clips/r004512.mp4", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100

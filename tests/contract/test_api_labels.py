"""API contract: sessions, rides, label work and Range-served review video."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from surfclip.api.app import create_app
from surfclip.store.schemas import Session
from tests.unit.test_labels import EXAMPLE

PROBE = {
    "path": "/videos/s.MP4",
    "container": "mp4",
    "codec": "h264",
    "width": 1280,
    "height": 720,
    "duration_s": 600.0,
    "avg_fps": 30.0,
    "is_vfr": False,
    "bit_depth": 8,
    "pix_fmt": "yuv420p",
    "hdr_format": "none",
}


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    root = tmp_path / "artifacts" / "abc123"
    root.mkdir(parents=True)
    session = Session(
        session_id="abc123",
        source_path="/videos/s.MP4",
        source_size=1,
        source_mtime=0,
        created_at=datetime(2026, 10, 14, tzinfo=UTC),
    )
    (root / "session.json").write_text(session.model_dump_json())
    (root / "probe.json").write_text(json.dumps(PROBE))
    (root / "rides.json").write_text(json.dumps(EXAMPLE))
    (root / "activity.json").write_text(json.dumps({"bin_s": 1.0, "values": [0.0, 0.5]}))
    (root / "review.mp4").write_bytes(bytes(range(256)) * 40)
    app = create_app(tmp_path / "artifacts", labels_dir=tmp_path / "labels")
    c = TestClient(app)
    c.labels_dir = tmp_path / "labels"  # type: ignore[attr-defined]
    return c


def test_sessions_list(client: TestClient) -> None:
    (s,) = client.get("/api/sessions").json()
    assert (s["session_id"], s["name"], s["rides"], s["short_attempts"]) == (
        "abc123",
        "s.MP4",
        1,
        1,
    )
    assert s["has_review_copy"] and s["labels_total"] == 2 and s["labels_done"] == 0


def test_unknown_session_uses_error_format(client: TestClient) -> None:
    r = client.get("/api/sessions/nope/rides")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "session_not_found"


def test_path_traversal_is_rejected(client: TestClient) -> None:
    assert client.get("/api/sessions/..%2F..%2Fetc/rides").status_code == 404


def test_label_work_round_trip_and_finalize(client: TestClient) -> None:
    work = client.get("/api/sessions/abc123/labels").json()
    assert [i["verdict"] for i in work["items"]] == ["?", "?"]
    assert client.post("/api/sessions/abc123/labels/finalize").status_code == 409
    work["items"][0]["verdict"] = "ok"
    work["items"][1]["verdict"] = "no"
    assert client.put("/api/sessions/abc123/labels", json=work).status_code == 200
    r = client.post("/api/sessions/abc123/labels/finalize")
    assert r.status_code == 200 and r.json()["rides"] == 1
    labels_dir: Path = client.labels_dir  # type: ignore[attr-defined]
    assert json.loads((labels_dir / "s.json").read_text())["rides"][0]["origin"] == "accepted"
    assert client.get("/api/sessions/abc123/labels").json()["finalized"]


def test_label_work_does_not_touch_rides_or_edits(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "artifacts" / "abc123"
    before = (root / "rides.json").read_bytes()
    work = client.get("/api/sessions/abc123/labels").json()
    work["items"][0]["verdict"] = "no"
    client.put("/api/sessions/abc123/labels", json=work)
    assert (root / "rides.json").read_bytes() == before
    assert not (root / "edits.json").exists()


def test_review_video_supports_range(client: TestClient) -> None:
    r = client.get("/api/sessions/abc123/media/review.mp4", headers={"Range": "bytes=100-199"})
    assert r.status_code == 206
    assert r.headers["content-range"] == "bytes 100-199/10240"
    assert len(r.content) == 100


def test_activity(client: TestClient) -> None:
    assert client.get("/api/sessions/abc123/activity").json()["values"] == [0.0, 0.5]


def test_static_ui_is_served_when_built(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>ui</html>")
    c = TestClient(create_app(tmp_path / "artifacts", web_dist=dist))
    assert "ui" in c.get("/").text

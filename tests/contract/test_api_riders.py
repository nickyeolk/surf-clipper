"""T011: API contract for rider labels (evaluation data; never changes rides or edits)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import surfclip.api.app as app_module
from surfclip.api.app import create_app
from surfclip.store.schemas import RiderGroup, Riders, Rides, Session
from tests.contract.test_api_labels import PROBE
from tests.unit.test_labels import EXAMPLE

S = "/api/sessions/abc123"


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Path]:
    root = tmp_path / "artifacts" / "abc123"
    root.mkdir(parents=True)
    session = Session(session_id="abc123", source_path="/videos/s.MP4", source_size=1,
                      source_mtime=0, created_at=datetime(2026, 10, 16, tzinfo=UTC))  # fmt: skip
    (root / "session.json").write_text(session.model_dump_json())
    (root / "probe.json").write_text(json.dumps(PROBE))
    (root / "rides.json").write_text(json.dumps(EXAMPLE))
    (root / "rides.detected.json").write_text(json.dumps(EXAMPLE))
    riders = Riders(
        session_id="abc123",
        descriptor="colour",
        riders=[RiderGroup(rider_id="g01", ride_ids=["r004512"])],
        assignments=[],
    )
    monkeypatch.setattr(
        app_module,
        "detected_grouping",
        lambda store, cfg: (Rides.model_validate(EXAMPLE), riders),
    )
    labels = tmp_path / "labels"
    client = TestClient(create_app(root.parent, labels_dir=labels / "rides"))
    return client, labels


def test_rider_labels_need_ride_labels_first(env: tuple[TestClient, Path]) -> None:
    client, _ = env
    r = client.get(f"{S}/rider-labels")
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_ride_labels"


def test_rider_label_round_trip(env: tuple[TestClient, Path], tmp_path: Path) -> None:
    client, labels = env
    (labels / "rides").mkdir(parents=True)
    (labels / "rides" / "s.json").write_text(
        json.dumps({"source": "s.MP4", "rides": [{"start_s": 150.4, "end_s": 171.9}]})
    )
    work = client.get(f"{S}/rider-labels").json()
    assert [(i["proposed"], i["detected_ride"]) for i in work["items"]] == [("Rider 1", "r004512")]
    assert client.post(f"{S}/rider-labels/finalize").status_code == 409
    work["items"][0]["rider"] = "me"
    work["named"] = ["me"]
    assert client.put(f"{S}/rider-labels", json=work).status_code == 200
    r = client.post(f"{S}/rider-labels/finalize")
    assert r.status_code == 200 and r.json() == {"rides": 1, "riders": 1}
    final = json.loads((labels / "riders" / "s.json").read_text())
    assert final["named"] == ["me"] and final["rides"][0]["rider"] == "me"
    root = tmp_path / "artifacts" / "abc123"
    assert json.loads((root / "rides.json").read_text()) == EXAMPLE
    assert not (root / "edits.json").exists()

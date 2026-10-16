"""004 T003: evaluation marks (times only; follow rides by span)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from surfclip.api.app import create_app
from surfclip.store.schemas import RiderGroup, Riders, Session
from tests.contract.test_api_labels import PROBE
from tests.unit.test_labels import EXAMPLE

S = "/api/sessions/abc123"


@pytest.fixture
def env(tmp_path: Path) -> tuple[TestClient, Path, Path]:
    root = tmp_path / "artifacts" / "abc123"
    root.mkdir(parents=True)
    session = Session(session_id="abc123", source_path="/videos/s.MP4", source_size=1,
                      source_mtime=0, created_at=datetime(2026, 10, 17, tzinfo=UTC))  # fmt: skip
    (root / "session.json").write_text(session.model_dump_json())
    (root / "probe.json").write_text(json.dumps(PROBE))
    (root / "rides.json").write_text(json.dumps(EXAMPLE))
    riders = Riders(
        session_id="abc123", descriptor="embedding",
        riders=[RiderGroup(rider_id="g1", name="me", ride_ids=["r004512"])], assignments=[],
    )  # fmt: skip
    (root / "riders.json").write_text(riders.model_dump_json())
    labels = tmp_path / "labels"
    client = TestClient(create_app(root.parent, labels_dir=labels / "rides"))
    return client, root, labels


def test_marks_round_trip(env: tuple[TestClient, Path, Path]) -> None:
    client, _, labels = env
    work = client.get(f"{S}/marks").json()
    assert work["source"] == "s.MP4" and not work["final"]
    assert [(r["ride_id"], r["ending"]) for r in work["rides"]] == [("r004512", None)]
    assert client.post(f"{S}/marks/finalize").status_code == 409  # ending missing
    work["rides"][0].update(turns=[155.0, 160.2], ending="fall")
    assert client.put(f"{S}/marks", json=work).status_code == 200
    done = client.post(f"{S}/marks/finalize")
    assert done.json() == {"rides": 1, "turns": 2, "falls": 1}
    saved = json.loads((labels / "analysis" / "s.json").read_text())
    assert saved["final"] and saved["rides"][0]["turns"] == [155.0, 160.2]
    assert "me" not in json.dumps(saved)  # no names in committed labels


def test_marks_follow_rides_by_span(env: tuple[TestClient, Path, Path]) -> None:
    client, root, _ = env
    work = client.get(f"{S}/marks").json()
    work["rides"][0].update(turns=[155.0], ending="exit")
    client.put(f"{S}/marks", json=work)
    rides = json.loads(json.dumps(EXAMPLE))
    rides["rides"][0].update(ride_id="r004513", start_s=150.6)  # re-run: new id, same ride
    (root / "rides.json").write_text(json.dumps(rides))
    riders = json.loads((root / "riders.json").read_text())
    riders["riders"][0]["ride_ids"] = ["r004513"]
    (root / "riders.json").write_text(json.dumps(riders))
    (ride,) = client.get(f"{S}/marks").json()["rides"]
    assert (ride["ride_id"], ride["turns"], ride["ending"]) == ("r004513", [155.0], "exit")

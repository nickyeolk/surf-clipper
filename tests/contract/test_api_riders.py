"""T011: API contract for rider labels (evaluation data; never changes rides or edits)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import surfclip.api.app as app_module
from surfclip.api.app import create_app
from surfclip.store.schemas import RideAssignment, RiderGroup, Riders, Rides, Session
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


@pytest.fixture
def grouped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Path]:
    root = tmp_path / "artifacts" / "abc123"
    root.mkdir(parents=True)
    session = Session(session_id="abc123", source_path="/videos/s.MP4", source_size=1,
                      source_mtime=0, created_at=datetime(2026, 10, 16, tzinfo=UTC))  # fmt: skip
    (root / "session.json").write_text(session.model_dump_json())
    (root / "probe.json").write_text(json.dumps(PROBE))
    two = json.loads(json.dumps(EXAMPLE))
    second = dict(two["rides"][0], ride_id="r009000", start_s=300.0, end_s=320.0,
                  start_frame=9000, end_frame=9600,
                  clip_start_s=298.5, clip_end_s=322.0)  # fmt: skip
    two["rides"].append(second)
    (root / "rides.json").write_text(json.dumps(two))
    (root / "rides.detected.json").write_text(json.dumps(two))
    riders = Riders(
        session_id="abc123",
        descriptor="embedding",
        riders=[
            RiderGroup(rider_id="g01", ride_ids=["r004512"], example_ride_id="r004512"),
            RiderGroup(rider_id="g02", ride_ids=["r009000"], example_ride_id="r009000"),
        ],
        assignments=[
            RideAssignment(ride_id="r004512", rider_id="g01", confidence=0.9),
            RideAssignment(ride_id="r009000", rider_id="g02", confidence=0.4),
        ],
    )
    (root / "riders.json").write_text(riders.model_dump_json())
    calls: list[str] = []
    monkeypatch.setattr(app_module, "refresh_riders", lambda store, cfg: calls.append("x"))
    return TestClient(create_app(root.parent, labels_dir=tmp_path / "labels" / "rides")), root


def test_riders_list_has_display_labels(grouped: tuple[TestClient, Path]) -> None:
    client, _ = grouped
    body = client.get(f"{S}/riders").json()
    assert [g["label"] for g in body["riders"]] == ["Rider 1", "Rider 2"]


def test_name_records_rides_and_examples(grouped: tuple[TestClient, Path]) -> None:
    client, root = grouped
    r = client.post(
        f"{S}/rider-edits", json={"op": "rider_name", "rider_id": "g01", "name": " me "}
    )
    assert r.status_code == 200
    payload = json.loads((root / "edits.json").read_text())["edits"][0]["payload"]
    assert payload == {"name": "me", "rides": {"r004512": [150.4, 171.9]},
                       "examples": {"r004512": [150.4, 171.9]}}  # fmt: skip


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"op": "rider_name", "rider_id": "g09", "name": "me"}, 404, "rider_not_found"),
        ({"op": "rider_name", "rider_id": "g01", "name": "  "}, 400, "invalid_edit"),
        ({"op": "rider_same_as", "rider_id": "g01", "other_rider_id": "g01"}, 400, "invalid_edit"),
        ({"op": "rider_mixed", "rider_id": "g01"}, 400, "invalid_edit"),
        ({"op": "ride_rider", "ride_id": "r000001", "name": "me"}, 404, "ride_not_found"),
        ({"op": "ride_rider", "ride_id": "r004512"}, 400, "invalid_edit"),
    ],
)
def test_invalid_rider_edits(
    grouped: tuple[TestClient, Path], body: dict[str, object], status: int, code: str
) -> None:
    client, root = grouped
    r = client.post(f"{S}/rider-edits", json=body)
    assert r.status_code == status and r.json()["error"]["code"] == code
    assert not (root / "edits.json").exists()


def test_rides_filtered_by_rider(grouped: tuple[TestClient, Path]) -> None:
    client, _ = grouped
    rides = client.get(f"{S}/rides").json()["rides"]
    assert [(r["ride_id"], r["rider"]) for r in rides] == [
        ("r004512", "Rider 1"),
        ("r009000", "Rider 2"),
    ]
    only = client.get(f"{S}/rides", params={"rider": "Rider 2"}).json()["rides"]
    assert [r["ride_id"] for r in only] == ["r009000"]
    assert (
        client.get(f"{S}/rides", params={"rider": "nobody"}).json()["error"]["code"]
        == "rider_not_found"
    )

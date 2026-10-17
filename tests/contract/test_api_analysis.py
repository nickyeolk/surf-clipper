"""004 T013/T027: analysis, keypoints, stars and trick tags over the API."""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from surfclip.analysis.pose import Keypoints, write_keypoints
from surfclip.api.app import create_app
from surfclip.store.schemas import (
    AnalysisFile,
    RideAnalysis,
    RiderGroup,
    Riders,
    RideSummary,
    Session,
)
from tests.contract.test_api_labels import PROBE
from tests.unit.test_labels import EXAMPLE

S = "/api/sessions/abc123"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    root = tmp_path / "artifacts" / "abc123"
    root.mkdir(parents=True)
    session = Session(session_id="abc123", source_path="/videos/s.MP4", source_size=1,
                      source_mtime=0, created_at=datetime(2026, 10, 17, tzinfo=UTC))  # fmt: skip
    (root / "session.json").write_text(session.model_dump_json())
    probe = {**PROBE, "width": 1920, "height": 1080}
    (root / "probe.json").write_text(json.dumps(probe))
    (root / "rides.json").write_text(json.dumps(EXAMPLE))
    riders = Riders(session_id="abc123", descriptor="embedding",
                    riders=[RiderGroup(rider_id="g1", name="me", ride_ids=["r004512"])],
                    assignments=[])  # fmt: skip
    (root / "riders.json").write_text(riders.model_dump_json())
    analysis = AnalysisFile(session_id="abc123", rides=[RideAnalysis(
        ride_id="r004512", span=(150.4, 171.9), rider="me", cache_key="k", keypoints_key="k",
        fps=15, t0=150.4, summary=RideSummary(length_s=21.5, turns=3, pumps=1))])  # fmt: skip
    (root / "analysis.json").write_text(analysis.model_dump_json())
    kp = np.zeros((2, 17, 3))
    kp[:, :, :2] = 300.0
    kp[:, :, 2] = 0.9
    kp[1, 0] = (np.nan, np.nan, np.nan)
    write_keypoints(root / "analysis" / "r004512.parquet", Keypoints(
        t=np.array([150.4, 150.47]), box=np.array([[100.0, 200, 400, 800]] * 2), kp=kp,
        other_iou=np.zeros(2)))  # fmt: skip
    return TestClient(create_app(root.parent))


def test_analysis_and_keypoints_in_review_pixels(client: TestClient) -> None:
    (ride,) = client.get(f"{S}/analysis").json()["rides"]
    assert ride["ride_id"] == "r004512" and ride["starred"] is False
    assert 0 <= ride["score"]["value"] <= 100 and ride["score"]["explanation"]
    kp = client.get(f"{S}/analysis/r004512/keypoints").json()
    assert (kp["width"], kp["height"]) == (1280, 720)  # review copy is 720p
    first = kp["frames"][0]
    assert first["box"] == [66.7, 133.3, 266.7, 533.3] and first["kp"][0] == [200.0, 200.0, 0.9]
    assert kp["frames"][1]["kp"][0] == [None, None, 0.0]
    assert client.get(f"{S}/analysis/r999/keypoints").status_code == 404


def test_stars_and_tricks_follow_the_ride(client: TestClient) -> None:
    assert client.post(f"{S}/stars", json={"ride_id": "r004512"}).status_code == 200
    assert client.get(f"{S}/analysis").json()["rides"][0]["starred"] is True
    client.post(f"{S}/stars", json={"ride_id": "r004512", "starred": False})
    assert client.get(f"{S}/analysis").json()["rides"][0]["starred"] is False
    tag = client.post(
        f"{S}/tricks", json={"ride_id": "r004512", "t": 160.0, "name": " 360 "}
    ).json()
    assert tag["name"] == "360"
    assert (
        client.post(f"{S}/tricks", json={"ride_id": "r004512", "t": 1, "name": " "}).status_code
        == 400
    )
    (listed,) = client.get("/api/tricks?name=360").json()
    assert (listed["ride_id"], listed["t"], listed["rider"]) == ("r004512", 160.0, "me")
    assert client.delete(f"{S}/tricks/{tag['edit_id']}").status_code == 204
    assert client.get("/api/tricks").json() == []
    assert client.delete(f"{S}/tricks/{tag['edit_id']}").status_code == 404

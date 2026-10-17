"""004: analysing chosen riders only; others keep their results; unnamed riders' data deleted."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import surfclip.analysis.service as service
import surfclip.stages as stages
from surfclip.analysis.pose import Keypoints
from surfclip.config import load_config
from surfclip.store.schemas import RideAnalysis, RiderGroup, Riders, RideSummary, Session
from surfclip.store.session import SessionStore
from tests.contract.test_api_labels import PROBE
from tests.unit.test_labels import EXAMPLE

CFG = load_config()


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SessionStore:
    root = tmp_path / "s1"
    root.mkdir()
    session = Session(session_id="s1", source_path="/v/s.MP4", source_size=1, source_mtime=0,
                      created_at=datetime(2026, 10, 17, tzinfo=UTC))  # fmt: skip
    st = SessionStore(root, session)
    st.save()
    (root / "probe.json").write_text(json.dumps(PROBE))
    rides = json.loads(json.dumps(EXAMPLE))
    second = {**rides["rides"][0], "ride_id": "r009000", "start_s": 300.0, "end_s": 320.0}
    rides["rides"].append(second)
    (root / "rides.json").write_text(json.dumps(rides))
    riders = Riders(session_id="s1", descriptor="embedding", assignments=[], riders=[
        RiderGroup(rider_id="g1", name="me", ride_ids=["r004512"]),
        RiderGroup(rider_id="g2", name="Pat", ride_ids=["r009000"]),
    ])  # fmt: skip
    (root / "riders.json").write_text(riders.model_dump_json())

    calls: list[str] = []
    kp = Keypoints(
        t=np.zeros(1), box=np.zeros((1, 4)), kp=np.zeros((1, 17, 3)), other_iou=np.zeros(1)
    )

    def fake_kp(info: Any, ride: Any, *a: Any, **k: Any) -> Keypoints:
        calls.append(ride.ride_id)
        return kp

    def fake_measure(
        store: Any, ride: Any, kp: Any, cfg: Any, rider: str, keys: tuple[str, str]
    ) -> RideAnalysis:
        return RideAnalysis(ride_id=ride.ride_id, span=(ride.start_s, ride.end_s), rider=rider,
                            cache_key=keys[0], keypoints_key=keys[1], fps=15, t0=ride.start_s,
                            summary=RideSummary(length_s=ride.length_s))  # fmt: skip

    monkeypatch.setattr(service, "ride_keypoints", fake_kp)
    monkeypatch.setattr(service, "PoseModel", lambda *a, **k: object())
    monkeypatch.setattr(service, "measure", fake_measure)
    monkeypatch.setattr(stages, "session_observations", lambda store: [])
    st.calls = calls  # type: ignore[attr-defined]
    return st


def test_only_chosen_riders_are_analysed_and_others_kept(store: SessionStore) -> None:
    calls: list[str] = store.calls  # type: ignore[attr-defined]
    result = service.analyse_session(store, CFG, riders=["ME"])  # case-insensitive
    assert calls == ["r004512"] and [a.rider for a in result.rides] == ["me"]
    result = service.analyse_session(store, CFG, riders=["pat"])
    assert calls == ["r004512", "r009000"]
    assert sorted(a.rider for a in result.rides) == ["Pat", "me"]  # me kept from before
    service.analyse_session(store, CFG)  # everyone named: both cached, nothing recomputed
    assert calls == ["r004512", "r009000"]
    store.path(service.ANALYSIS_FILE).unlink()  # as if a run was stopped before writing it
    service.analyse_session(store, CFG)
    assert calls == ["r004512", "r009000"]  # keypoints on disk carry their key: reused


def test_unnamed_riders_lose_their_body_data(store: SessionStore) -> None:
    service.analyse_session(store, CFG)
    kp_dir = store.path(service.KEYPOINT_DIR)
    assert {p.stem for p in kp_dir.glob("*.parquet")} == {"r004512", "r009000"}
    riders = json.loads(store.path("riders.json").read_text())
    riders["riders"][1]["name"] = None  # Pat is no longer named
    store.path("riders.json").write_text(json.dumps(riders))
    result = service.analyse_session(store, CFG, riders=["me"])
    assert {p.stem for p in kp_dir.glob("*.parquet")} == {"r004512"}
    assert [a.rider for a in result.rides] == ["me"]

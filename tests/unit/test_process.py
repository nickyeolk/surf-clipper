"""Session processing for the browser UI: the zone proposal is used automatically when reliable."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import surfclip.stages as stages_module
import surfclip.zone.editing as editing_module
from surfclip.config import DEFAULT_CONFIG_PATH
from surfclip.edits.log import confirmed_zone, read_edits
from surfclip.process import process_session
from surfclip.store.schemas import Session, Zone, ZoneCorners
from surfclip.store.session import SessionStore
from surfclip.zone.propose import ZoneProposal
from tests.unit.test_labels import EXAMPLE

ZONE = Zone(
    epoch_id=0,
    corners=ZoneCorners(
        back_a=(100, 100), back_b=(900, 100), front_a=(0, 700), front_b=(1000, 700)
    ),
    origin="proposed",
    proposal_confidence=0.9,
)


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    root = tmp_path / "s1"
    root.mkdir()
    return SessionStore(
        root,
        Session(session_id="s1", source_path="/v.mp4", source_size=1, source_mtime=0,
                created_at=datetime(2026, 10, 16, tzinfo=UTC)),
    )  # fmt: skip


def fake_pipeline(store: SessionStore, until_seen: list[str | None]):  # type: ignore[no-untyped-def]
    class P:
        def run(self, _store, _cfg, *, until=None, progress=None):  # type: ignore[no-untyped-def]
            until_seen.append(until)
            if until == "rides":
                (store.root / "rides.json").write_text(json.dumps(EXAMPLE))

    return P


@pytest.mark.parametrize("unreliable", [False, True])
def test_reliable_proposal_is_used_automatically(
    store: SessionStore, monkeypatch: pytest.MonkeyPatch, unreliable: bool
) -> None:
    runs: list[str | None] = []
    monkeypatch.setattr(stages_module, "default_pipeline", fake_pipeline(store, runs))
    proposal = ZoneProposal(zone=ZONE, confidence=0.9, unreliable=unreliable, points=5000)
    monkeypatch.setattr(editing_module, "zone_proposal", lambda _s: proposal)
    result = process_session(store, DEFAULT_CONFIG_PATH, lambda f, m: None)
    zone = confirmed_zone(read_edits(store))
    if unreliable:
        assert runs == ["track"] and result["next"] == "zone" and zone is None
    else:
        assert runs == ["track", "rides"] and result == {
            "next": "review",
            "rides": 1,
            "zone": "proposed",
        }
        assert zone is not None and zone.origin == "proposed"
        assert read_edits(store).edits[0].payload["how"] == "auto"

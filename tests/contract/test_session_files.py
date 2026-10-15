"""The JSON examples in contracts/session-files.md must validate against the models (T010)."""

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from surfclip.store.schemas import SCHEMA_VERSION, Edits, Rides

CONTRACT = (
    Path(__file__).parents[2]
    / "specs"
    / "001-ride-detection-clipping"
    / "contracts"
    / "session-files.md"
)


def _json_blocks() -> dict[str, dict[str, object]]:
    text = CONTRACT.read_text(encoding="utf-8")
    blocks: dict[str, dict[str, object]] = {}
    for heading, body in re.findall(r"## `([\w.]+)`.*?```json\n(.*?)```", text, re.S):
        blocks[heading] = json.loads(body)
    return blocks


def test_contract_has_rides_and_edits_examples() -> None:
    assert {"rides.json", "edits.json"} <= _json_blocks().keys()


def test_rides_example_validates_and_round_trips() -> None:
    example = _json_blocks()["rides.json"]
    rides = Rides.model_validate(example)
    assert rides.schema_version == SCHEMA_VERSION
    assert rides.rides[0].start_kind == "acid_drop"
    assert json.loads(rides.model_dump_json()) == json.loads(json.dumps(example))


def test_edits_example_validates() -> None:
    edits = Edits.model_validate(_json_blocks()["edits.json"])
    assert [e.op for e in edits.edits] == ["confirm_zone", "trim", "undo"]


def test_short_detected_ride_is_rejected_but_user_added_is_kept() -> None:
    example = _json_blocks()["rides.json"]
    ride = example["rides"][0]  # type: ignore[index]
    short = {**ride, "end_s": ride["start_s"] + 5}  # type: ignore[index,operator]
    with pytest.raises(ValidationError, match="shorter than min_length_s"):
        Rides.model_validate({**example, "rides": [short]})
    added = {**short, "flags": {**short["flags"], "user_added": True}}
    Rides.model_validate({**example, "rides": [added]})


def test_end_before_start_is_rejected() -> None:
    example = _json_blocks()["rides.json"]
    ride = example["rides"][0]  # type: ignore[index]
    bad = {**ride, "end_s": ride["start_s"] - 1}  # type: ignore[index,operator]
    with pytest.raises(ValidationError, match="end_s must be after start_s"):
        Rides.model_validate({**example, "rides": [bad]})


def test_edit_ids_must_be_sequential() -> None:
    edits = _json_blocks()["edits.json"]
    entries = edits["edits"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="append-only"):
        Edits.model_validate({**edits, "edits": list(reversed(entries))})  # type: ignore[arg-type]

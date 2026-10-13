"""Hand-made zone files in labels/zones/ must parse and give a valid pool mapping."""

from pathlib import Path

import pytest

from surfclip.store.schemas import Zone
from surfclip.zone.geometry import PoolMapping

ZONES = sorted((Path(__file__).parents[2] / "labels" / "zones").glob("*.json"))


def test_zone_files_exist() -> None:
    assert ZONES, "expected hand-made zones in labels/zones/"


@pytest.mark.parametrize("path", ZONES, ids=[p.stem for p in ZONES])
def test_zone_file_is_valid(path: Path) -> None:
    zone = Zone.model_validate_json(path.read_text(encoding="utf-8"))
    PoolMapping.from_corners(zone.corners)
    assert zone.entry_walls

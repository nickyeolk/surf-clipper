import csv
from pathlib import Path

import pytest

from surfclip.eval.labels import LabelError, fmt_time, import_csv, parse_time, propose
from surfclip.store.schemas import Rides

EXAMPLE = {
    "session_id": "abc",
    "source": {"path": "x.mp4", "fps": 30.0, "hdr_format": "none"},
    "settings": {"min_length_s": 10, "pad_before_s": 1.0, "pad_after_s": 1.5},
    "rides": [
        {
            "ride_id": "r004512",
            "start_s": 150.4,
            "end_s": 171.9,
            "start_frame": 4512,
            "end_frame": 5157,
            "clip_start_s": 149.4,
            "clip_end_s": 173.4,
            "confidence": 0.87,
            "epochs": [0],
            "track_ids": [17],
            "start_kind": "acid_drop",
        }
    ],
    "short_attempts": [
        {"ride_id": "s006021", "start_s": 200.7, "end_s": 205.1, "confidence": 0.71}
    ],
}


def test_time_round_trip() -> None:
    assert fmt_time(150.4) == "02:30.40"
    assert fmt_time(3725.5) == "1:02:05.50"
    assert parse_time("02:30.40") == pytest.approx(150.4)
    assert parse_time("1:02:05.5") == pytest.approx(3725.5)
    with pytest.raises(LabelError):
        parse_time("2m30")


def _edit(path: Path, changes: dict[int, dict[str, str]], extra: list[dict[str, str]]) -> None:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for i, ch in changes.items():
        rows[i].update(ch)
    rows += extra
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def test_propose_then_import(tmp_path: Path) -> None:
    out = tmp_path / "s.csv"
    assert propose(Rides.model_validate(EXAMPLE), out) == 2
    _edit(
        out,
        {0: {"verdict": "ok"}, 1: {"verdict": "no"}},
        [
            {
                "id": "",
                "start": "",
                "end": "",
                "verdict": "add",
                "new_start": "05:00",
                "new_end": "05:20.5",
                "acid_drop": "yes",
            }
        ],
    )
    labels = import_csv(out, "x.mp4")
    assert [(r.start_s, r.end_s, r.acid_drop, r.origin) for r in labels.rides] == [
        (150.4, 171.9, True, "accepted"),
        (300.0, 320.5, True, "added"),
    ]


def test_unvalidated_rows_are_refused(tmp_path: Path) -> None:
    out = tmp_path / "s.csv"
    propose(Rides.model_validate(EXAMPLE), out)
    with pytest.raises(LabelError, match="verdict not set"):
        import_csv(out, "x.mp4")


def test_fix_uses_new_times(tmp_path: Path) -> None:
    out = tmp_path / "s.csv"
    propose(Rides.model_validate(EXAMPLE), out)
    _edit(out, {0: {"verdict": "fix", "new_start": "02:29.90"}, 1: {"verdict": "no"}}, [])
    labels = import_csv(out, "x.mp4")
    assert labels.rides[0].start_s == pytest.approx(149.9)
    assert labels.rides[0].end_s == pytest.approx(171.9)
    assert labels.rides[0].origin == "corrected"

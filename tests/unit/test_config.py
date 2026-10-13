from pathlib import Path

import pytest

from surfclip.config import ConfigError, load_config

DEFAULT = Path(__file__).parents[2] / "config" / "default.toml"


def test_default_config_loads_with_spec_defaults() -> None:
    cfg = load_config(DEFAULT)
    assert cfg.rides.confirm_window_s == 1.5
    assert cfg.rides.min_length_s == 10.0
    assert cfg.rides.pad_before_s == 1.0
    assert cfg.rides.pad_after_s == 1.5
    assert cfg.rides.frame_edge_grace_s == 2.0
    assert cfg.analysis.fps == 5
    assert cfg.server.host == "127.0.0.1"


def test_dotted_overrides_apply_and_coerce() -> None:
    cfg = load_config(DEFAULT, {"rides.min_length_s": 15, "detect.tiling": "always"})
    assert cfg.rides.min_length_s == 15.0
    assert cfg.detect.tiling == "always"


def test_unknown_override_key_is_rejected() -> None:
    with pytest.raises(ConfigError, match=r"rides\.min_lenght_s"):
        load_config(DEFAULT, {"rides.min_lenght_s": 15})


def test_invalid_value_is_rejected() -> None:
    with pytest.raises(ConfigError):
        load_config(DEFAULT, {"detect.tiling": "sometimes"})


def test_server_must_stay_on_loopback() -> None:
    with pytest.raises(ConfigError, match="loopback"):
        load_config(DEFAULT, {"server.host": "0.0.0.0"})


def test_section_hash_changes_only_with_that_section() -> None:
    a = load_config(DEFAULT)
    b = load_config(DEFAULT, {"rides.min_length_s": 12})
    assert a.section_hash("detect") == b.section_hash("detect")
    assert a.section_hash("rides") != b.section_hash("rides")

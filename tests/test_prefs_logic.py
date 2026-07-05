"""Tests for prefs.py pure logic (no GTK windows are created).

These cover the non-widget parts of the Preferences window: the
update_config None guard, and on-disk value type coercion.
"""
from types import SimpleNamespace

from talktype.prefs import PreferencesWindow, _coerce_config_types


def _dummy(config=None):
    """Bare stand-in for a PreferencesWindow instance."""
    return SimpleNamespace(config=config if config is not None else {})


# --- update_config: combo rebuilds emit changed with active_id=None ---

def test_update_config_ignores_none_value():
    """A GTK combo emits 'changed' with get_active_id()=None during
    remove_all(); writing that None to config produced 'device = None'
    in the TOML file, which is unparseable and wiped all settings."""
    d = _dummy({"device": "cpu"})
    PreferencesWindow.update_config(d, "device", None)
    assert d.config["device"] == "cpu"  # unchanged


def test_update_config_sets_real_values():
    d = _dummy({"device": "cpu"})
    PreferencesWindow.update_config(d, "model", "medium")
    assert d.config["model"] == "medium"


# --- type coercion of on-disk values against Settings field types ---

def test_coerce_config_types_fixes_string_numbers():
    """Configs written by the old hand-rolled parser era can contain
    '5' instead of 5 — which crashed the window at build time."""
    d = {"auto_timeout_minutes": "5", "indicator_offset_x": "0", "model": "small"}
    out = _coerce_config_types(d)
    assert out["auto_timeout_minutes"] == 5
    assert out["indicator_offset_x"] == 0
    assert out["model"] == "small"


def test_coerce_config_types_fixes_string_bools():
    d = {"beeps": "false", "notify": "true"}
    out = _coerce_config_types(d)
    assert out["beeps"] is False
    assert out["notify"] is True


def test_coerce_config_types_leaves_correct_types_alone():
    d = {"beeps": True, "auto_timeout_minutes": 7, "language": "es", "custom_key": [1]}
    out = _coerce_config_types(d)
    assert out["beeps"] is True
    assert out["auto_timeout_minutes"] == 7
    assert out["language"] == "es"
    assert out["custom_key"] == [1]  # unknown keys untouched

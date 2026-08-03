"""Tests for prefs.py pure logic (no GTK windows are created).

These cover the non-widget parts of the Preferences window: the
update_config None guard, on-disk value type coercion, and that the
window's own writer produces a file config.py can read back.
"""
import tomllib
from types import SimpleNamespace

from talktype import prefs as P
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


# --- save_config must emit TOML that can be read back ---

def _saveable(tmp_path, monkeypatch, config, at_open=None):
    """A stand-in window whose save_config() writes to a throwaway path."""
    monkeypatch.setattr(P, "CONFIG_PATH", str(tmp_path / "config.toml"))
    return SimpleNamespace(config=dict(config),
                           _config_at_open=dict(at_open if at_open is not None else {}))


def test_save_config_escapes_double_quotes(tmp_path, monkeypatch):
    """A microphone name containing a double quote must survive Apply.

    config.py's writer escapes these via _toml_string, but the Preferences
    window had its own unescaped copy of the serializer: one Apply click
    wrote `mic = "Blue Yeti "Nano" USB"`, which is invalid TOML, so the
    next load quarantined the file and reset every setting — including the
    hotkey, which defaults to blank and silently kills dictation.
    """
    d = _saveable(tmp_path, monkeypatch,
                  {"mic": 'Blue Yeti "Nano" USB', "hotkey": "F8", "language_mode": "auto"})

    assert PreferencesWindow.save_config(d) is True

    data = tomllib.loads((tmp_path / "config.toml").read_text())
    assert data["mic"] == 'Blue Yeti "Nano" USB'
    assert data["hotkey"] == "F8"


def test_save_config_escapes_backslashes(tmp_path, monkeypatch):
    d = _saveable(tmp_path, monkeypatch,
                  {"mic": r"Mic\Device", "hotkey": "F8", "language_mode": "auto"})

    assert PreferencesWindow.save_config(d) is True

    data = tomllib.loads((tmp_path / "config.toml").read_text())
    assert data["mic"] == r"Mic\Device"


def test_save_config_roundtrips_through_config_loader(tmp_path, monkeypatch):
    """The file Preferences writes must be readable by config.load_config,
    not merely by tomllib — the two must agree on the same escaping."""
    from talktype import config as C

    d = _saveable(tmp_path, monkeypatch,
                  {"mic": 'Blue Yeti "Nano" USB', "hotkey": "F8",
                   "model": "large-v3", "language_mode": "auto"})
    assert PreferencesWindow.save_config(d) is True

    monkeypatch.setattr(C, "CONFIG_PATH", str(tmp_path / "config.toml"))
    monkeypatch.setattr(C, "_config_cache", None)
    monkeypatch.setattr(C, "_config_mtime", None)
    s = C.load_config()
    assert s.mic == 'Blue Yeti "Nano" USB'
    assert s.hotkey == "F8"          # not reset to the blank default
    assert s.model == "large-v3"


# --- a damaged commands file must not wedge Apply/OK -----------------------

def test_saving_commands_over_a_damaged_file_does_not_raise(tmp_path, monkeypatch):
    """save_custom_commands now refuses to overwrite a file it could not
    read. _save_custom_commands runs FIRST in both on_apply and on_ok, so
    letting that propagate would make clicking OK do nothing at all — the
    window would not even close. It must degrade, not wedge.
    """
    from talktype import config as C

    path = tmp_path / "custom_commands.toml"
    path.write_text('[commands]\nbroken {{{\n')
    monkeypatch.setattr(C, "CUSTOM_COMMANDS_PATH", str(path))
    monkeypatch.setattr(C, "_commands_read_failed", False, raising=False)

    C.load_custom_commands()                     # fails -> flag set
    damaged = path.read_text()

    d = SimpleNamespace(commands_store=[["talk type", "TalkType"]])
    assert PreferencesWindow._save_custom_commands(d) is False

    assert path.read_text() == damaged, "damaged commands file was overwritten"


def test_saving_commands_normally_reports_success(tmp_path, monkeypatch):
    from talktype import config as C

    path = tmp_path / "custom_commands.toml"
    monkeypatch.setattr(C, "CUSTOM_COMMANDS_PATH", str(path))
    monkeypatch.setattr(C, "_commands_read_failed", False, raising=False)

    d = SimpleNamespace(commands_store=[["talk type", "TalkType"]])
    assert PreferencesWindow._save_custom_commands(d) is True
    assert C.load_custom_commands() == {"talk type": "TalkType"}


# --- Preferences must not write over a config it could not read ------------

def test_save_config_refuses_when_the_file_on_disk_is_damaged(tmp_path, monkeypatch):
    """Opening Preferences over an unparseable config showed bare defaults
    (hotkey blank, model small). Clicking OK then wrote those defaults AND
    copied the damaged file over config.toml.bak — destroying the only
    surviving copy of the user's real settings in one click.
    """
    cfg = tmp_path / "config.toml"
    bak = tmp_path / "config.toml.bak"
    bak.write_text('# TalkType config\nmodel = "large-v3"\nhotkey = "F8"\n')
    good_backup = bak.read_text()
    cfg.write_text('# TalkType config\nmic = "Blue Yeti "Nano" USB"\n')
    damaged = cfg.read_text()

    monkeypatch.setattr(P, "CONFIG_PATH", str(cfg))
    d = SimpleNamespace(config={"hotkey": "", "model": "small", "language_mode": "auto"},
                        _config_at_open={"hotkey": "", "model": "small",
                                         "language_mode": "auto"})

    assert PreferencesWindow.save_config(d) is False

    assert cfg.read_text() == damaged, "damaged config was overwritten with defaults"
    assert bak.read_text() == good_backup, "good backup was destroyed"


def test_save_config_still_writes_when_the_file_is_readable(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text('# TalkType config\nmodel = "large-v3"\n')
    monkeypatch.setattr(P, "CONFIG_PATH", str(cfg))

    d = SimpleNamespace(config={"model": "medium", "language_mode": "auto"},
                        _config_at_open={"model": "large-v3", "language_mode": "auto"})

    assert PreferencesWindow.save_config(d) is True
    assert tomllib.loads(cfg.read_text())["model"] == "medium"


# --- the hotkey dropdown must not display one value and save another -------

class FakeCombo:
    """Minimal ComboBoxText stand-in: records the id set on it."""

    def __init__(self):
        self.active_id = None
        self._handlers = []

    def set_active_id(self, value):
        self.active_id = value

    def get_active_id(self):
        return self.active_id

    def connect(self, signal, handler):
        self._handlers.append((signal, handler))


def test_hotkey_fallback_is_written_into_the_config(monkeypatch):
    """When no hotkey is configured (Settings default is ""), the dropdown
    falls back to displaying F8 — but self.config kept "".

    Clicking OK therefore saved a blank hotkey while the screen said F8, and
    re-selecting F8 emits no 'changed' signal because it is already active.
    A user whose onboarding was interrupted has dead dictation and the one
    screen they would use to fix it cannot fix it.
    """
    d = SimpleNamespace(config={"hotkey": "", "toggle_hotkey": ""},
                        hotkey_combo=FakeCombo(),
                        toggle_combo=FakeCombo())

    PreferencesWindow._apply_hotkey_fallbacks(d, ["F8", "F9", "F10"])

    assert d.hotkey_combo.get_active_id() == "F8"
    assert d.config["hotkey"] == "F8", "screen shows F8 but a blank hotkey would be saved"
    assert d.toggle_combo.get_active_id() == "F9"
    assert d.config["toggle_hotkey"] == "F9"


def test_a_configured_hotkey_is_left_alone(monkeypatch):
    d = SimpleNamespace(config={"hotkey": "F10", "toggle_hotkey": "F9"},
                        hotkey_combo=FakeCombo(),
                        toggle_combo=FakeCombo())

    PreferencesWindow._apply_hotkey_fallbacks(d, ["F8", "F9", "F10"])

    assert d.hotkey_combo.get_active_id() == "F10"
    assert d.config["hotkey"] == "F10"

"""Paste Last Dictation: a hotkey (Ctrl+Alt+P by default) that types the last
dictation again, for when it went to the wrong window.

It types only once every key of the combo is let go: typing while Ctrl and
Alt are still held would turn each letter into a Ctrl+Alt shortcut.
"""
import pytest
from evdev import ecodes

from tuxtalk import app, config, history, kwin_hotkeys

P = ecodes.KEY_P
CTRL, ALT = ecodes.KEY_LEFTCTRL, ecodes.KEY_LEFTALT
COMBO = ({"CTRL", "ALT"}, P)


class Event:
    def __init__(self, code, value):
        self.type, self.code, self.value = ecodes.EV_KEY, code, value


class Cfg:
    beeps = False
    notify = False
    injection_mode = "type"
    auto_space = True


@pytest.fixture
def keys(monkeypatch):
    """A fake keyboard: grabs, typing and the Recent Dictations list recorded."""
    seen = {"grabbed": 0, "released": 0, "typed": [], "beeps": []}
    monkeypatch.setattr(app, "_grab_keyboards_hiding", lambda devs, codes: seen.__setitem__("grabbed", seen["grabbed"] + 1))
    monkeypatch.setattr(app, "_release_all_grabs", lambda: seen.__setitem__("released", seen["released"] + 1))
    monkeypatch.setattr(app, "_inject_text", lambda text, mode, t0: seen["typed"].append((text, mode)) or "ok")
    monkeypatch.setattr(app, "_beep", lambda on, *a: seen["beeps"].append(a))
    monkeypatch.setattr(history, "get_entries", lambda: ["Hello there.\nSecond line.", "older"])
    monkeypatch.setattr(app.state, "is_recording", False)
    monkeypatch.setattr(app.state, "paste_last", None, raising=False)
    return seen


def send(code, value, held, combo=COMBO):
    """Deliver one key event the way the main loop does: modifier state first."""
    if code in (CTRL, ALT):
        (held.add if value else held.discard)(code)
    app._handle_key_event(Event(code, value), "hold", ecodes.KEY_F8, None,
                          None, held, [], Cfg(), 0, paste_last_combo=combo)


def press_combo(held):
    send(CTRL, 1, held)
    send(ALT, 1, held)
    send(P, 1, held)


def test_types_the_last_dictation_once_every_key_is_up(keys):
    held = set()
    press_combo(held)
    assert keys["grabbed"] == 1 and keys["typed"] == []      # P still down
    send(P, 0, held)
    assert keys["typed"] == []                                # Ctrl, Alt still down
    send(ALT, 0, held)
    assert keys["typed"] == []
    send(CTRL, 0, held)
    assert keys["typed"] == [("Hello there.§SHIFT_ENTER§Second line. ", "type")]
    assert keys["released"] >= 1


def test_modifiers_let_go_before_the_key_works_too(keys):
    held = set()
    press_combo(held)
    send(CTRL, 0, held)
    send(ALT, 0, held)
    assert keys["typed"] == []
    send(P, 0, held)
    assert len(keys["typed"]) == 1


def test_it_fires_once_per_press(keys):
    held = set()
    press_combo(held)
    for code in (P, ALT, CTRL):
        send(code, 0, held)
    send(ecodes.KEY_A, 0, held)                               # a later unrelated release
    assert len(keys["typed"]) == 1


def test_nothing_dictated_yet_gives_the_cancel_beep(keys, monkeypatch):
    monkeypatch.setattr(history, "get_entries", lambda: [])
    held = set()
    press_combo(held)
    for code in (P, ALT, CTRL):
        send(code, 0, held)
    assert keys["typed"] == [] and keys["beeps"] == [app.CANCEL_BEEP]
    assert keys["released"] >= 1


def test_not_while_recording(keys, monkeypatch):
    monkeypatch.setattr(app.state, "is_recording", True)
    held = set()
    press_combo(held)
    assert keys["grabbed"] == 0


def test_without_a_combo_nothing_happens(keys):
    held = set()
    send(CTRL, 1, held, combo=None)
    send(P, 1, held, combo=None)
    send(P, 0, held, combo=None)
    send(CTRL, 0, held, combo=None)
    assert keys["grabbed"] == 0 and keys["typed"] == []


def test_no_trailing_space_without_auto_space(keys, monkeypatch):
    monkeypatch.setattr(Cfg, "auto_space", False)
    held = set()
    press_combo(held)
    for code in (P, ALT, CTRL):
        send(code, 0, held)
    assert keys["typed"][0][0] == "Hello there.§SHIFT_ENTER§Second line."


# --- the setting ----------------------------------------------------------------

def test_on_by_default_and_applied_without_a_restart():
    assert config.Settings().paste_last_hotkey == "Ctrl+Alt+P"
    assert "paste_last_hotkey" in config.LIVE_APPLIED_KEYS


def test_kde_and_gnome_hold_it_back_from_the_focused_app():
    cfg = config.Settings(hotkey="F8", toggle_hotkey="F9")
    names = [name for name, _what, _key in kwin_hotkeys.wanted_shortcuts(cfg)]
    assert any("paste-last" in n for n in names)


def test_preferences_offers_it():
    import pathlib
    prefs = (pathlib.Path(app.__file__).parent / "prefs.py").read_text()
    assert '"paste_last_hotkey"' in prefs
    assert "Paste Last Dictation" in prefs


# --- telling people it exists ------------------------------------------------------
# Where they'd need it: the "couldn't type that" notification, the Recent
# Dictations menu, and the tips at the end of first-time setup.

import pathlib

SRC = pathlib.Path(app.__file__).parent


@pytest.mark.parametrize("outcome", ["failed", "partial"])
def test_the_undelivered_notice_offers_the_hotkey(outcome, monkeypatch):
    told = []
    monkeypatch.setattr(app, "_notify", lambda title, msg: told.append(msg))
    monkeypatch.setattr(app, "_beep", lambda *a: None)
    monkeypatch.setattr(app, "_paste_last_hotkey", "Ctrl+Alt+P")
    import tuxtalk.uinput_helper as uh
    monkeypatch.setattr(uh, "typing_blocked_reason", lambda: None)
    app._report_undelivered(outcome, False)
    assert "Or press Ctrl+Alt+P to type it again where your cursor is." in told[0]


def test_no_hint_when_the_hotkey_is_off(monkeypatch):
    told = []
    monkeypatch.setattr(app, "_notify", lambda title, msg: told.append(msg))
    monkeypatch.setattr(app, "_beep", lambda *a: None)
    monkeypatch.setattr(app, "_paste_last_hotkey", "")
    import tuxtalk.uinput_helper as uh
    monkeypatch.setattr(uh, "typing_blocked_reason", lambda: None)
    app._report_undelivered("failed", False)
    assert "Ctrl+Alt+P" not in told[0]


def test_the_hint_text():
    assert history.paste_last_hint("Ctrl+Super+P") == "Ctrl+Super+P types the newest one again"
    assert history.paste_last_hint("") is None


def test_the_recent_dictations_menu_says_so_in_both_menus():
    tray = (SRC / "tray.py").read_text()
    assert "paste_last_hint(" in tray
    ext = next((SRC.parent.parent / "gnome-extension").glob("*/extension.js")).read_text()
    assert "GetPasteLastHotkey" in ext and "types the newest one again" in ext


def test_the_tray_tells_the_extension_the_key(monkeypatch):
    from tuxtalk import dbus_service
    monkeypatch.setattr(config, "load_config", lambda: config.Settings(paste_last_hotkey="Ctrl+Super+P"))
    assert dbus_service.TuxTalkDBusService.GetPasteLastHotkey(object()) == "Ctrl+Super+P"


def test_the_setup_tips_mention_it():
    welcome = (SRC / "welcome_dialog.py").read_text()
    assert "to type it again" in welcome and "paste_last_hotkey" in welcome


def _labels(widget):
    """Every label's text inside a GTK widget or menu."""
    from gi.repository import Gtk
    out = []
    if isinstance(widget, Gtk.Label):
        out.append(widget.get_text())
    if isinstance(widget, Gtk.MenuItem) and widget.get_label():
        out.append(widget.get_label())
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            out += _labels(child)
    return out


def test_the_tray_menu_line_really_appears(monkeypatch):
    """Runs the real menu code: a missing import here only fails when a user
    opens Recent Dictations."""
    import types
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    from tuxtalk import tray
    monkeypatch.setattr(config, "load_config", lambda: config.Settings(paste_last_hotkey="Ctrl+Alt+P"))
    monkeypatch.setattr(history, "get_entries", lambda: ["Hello there."])
    fake = types.SimpleNamespace(history_menu=Gtk.Menu(),
                                 _build_history_entry_submenu=lambda text, i: Gtk.Menu(),
                                 _clear_history=lambda: None)
    tray.DictationTray._fill_history_menu(fake, fake.history_menu)
    assert "Ctrl+Alt+P types the newest one again" in _labels(fake.history_menu)


def test_the_setup_tip_really_appears(monkeypatch):
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    from tuxtalk import welcome_dialog
    monkeypatch.setattr(config, "load_config", lambda: config.Settings(paste_last_hotkey="Ctrl+Alt+P"))
    seen = []

    def fake_run(dialog):
        seen.extend(_labels(dialog))
        return Gtk.ResponseType.OK
    monkeypatch.setattr(Gtk.Dialog, "run", fake_run)
    welcome_dialog.show_tips_and_features_dialog()
    assert any("Press Ctrl+Alt+P to type it again" in text for text in seen)


def test_a_hold_started_while_the_combo_is_pending_still_stops(keys, monkeypatch):
    """While the combo waits for its keys to be let go, the hold key's release
    must still get through, or an F8 recording started in that moment keeps
    running after F8 is let go."""
    stopped = []
    monkeypatch.setattr(app, "start_recording",
                        lambda *a, **k: setattr(app.state, "is_recording", True) or True)
    monkeypatch.setattr(app, "stop_recording",
                        lambda *a, **k: stopped.append(True) or setattr(app.state, "is_recording", False))
    monkeypatch.setattr(Cfg, "smart_quotes", False, raising=False)
    monkeypatch.setattr(Cfg, "language", None, raising=False)
    monkeypatch.setattr(Cfg, "auto_period", True, raising=False)
    held = set()
    press_combo(held)
    send(P, 0, held)                 # Ctrl and Alt still down: paste pending
    send(ecodes.KEY_F8, 1, held)
    send(ecodes.KEY_F8, 0, held)
    assert stopped, "the hold key's release was swallowed"


@pytest.mark.parametrize("on", [True, False])
def test_the_saving_battery_tip_appears_only_when_power_saving_is_on(monkeypatch, on):
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    from tuxtalk import welcome_dialog
    monkeypatch.setattr(config, "load_config", lambda: config.Settings(
        hotkey="F8", toggle_hotkey="F9", auto_timeout_enabled=on, auto_timeout_minutes=5))
    seen = []

    def fake_run(dialog):
        seen.extend(_labels(dialog))
        return Gtk.ResponseType.OK
    monkeypatch.setattr(Gtk.Dialog, "run", fake_run)
    welcome_dialog.show_tips_and_features_dialog()
    tip = [t for t in seen if "turns dictation off to save battery" in t]
    assert bool(tip) is on
    if on:
        assert "After 5 minutes without dictating" in tip[0] and "F8 and F9 do nothing" in tip[0]

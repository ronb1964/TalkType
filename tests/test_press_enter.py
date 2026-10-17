"""Ending a dictation with "press enter" sends a real Enter (enter_command.py).

Ron, 2026-10-17: "I really like the press enter, so you can just speak."
A spoken "new line" stays Shift+Enter, which never sends a chat message.
"""
import numpy as np
import pytest

from tuxtalk import app, config
from tuxtalk.enter_command import split_press_enter


@pytest.mark.parametrize("raw, expected", [
    ("See you at noon, press enter", ("See you at noon", True)),
    ("See you at noon. Press Enter.", ("See you at noon.", True)),
    ("What time is it? Press enter", ("What time is it?", True)),
    ("Thanks! Press return.", ("Thanks!", True)),
    ("git status press enter", ("git status", True)),
    ("Hit the enter key!", ("", True)),
    ("Press enter.", ("", True)),
    # Only the very end counts.
    ("press enter to continue the install", ("press enter to continue the install", False)),
    ("I like it", ("I like it", False)),
    ("", ("", False)),
    # "literal" types the words, like "literal new line".
    ("Type literal press enter", ("Type press enter", False)),
])
def test_split_press_enter(raw, expected):
    assert split_press_enter(raw) == expected


def _dictate(monkeypatch, raw, prepared=None, outcome="ok"):
    """Run one dictation through _transcribe_and_inject; what was typed and
    whether Enter was pressed, in order."""
    events = []
    monkeypatch.setattr(app, "_transcribe_audio", lambda audio, language: raw)
    if prepared is not None:
        monkeypatch.setattr(app, "_prepare_text", lambda r, *a, **k: prepared(r))
    monkeypatch.setattr(app, "_beep", lambda *a, **k: None)
    monkeypatch.setattr(app, "_handle_undo", lambda *a, **k: False)
    monkeypatch.setattr(app, "_handle_navigation", lambda *a, **k: False)
    monkeypatch.setattr(app, "_handle_fix_word", lambda *a, **k: False)
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: "kwrite")
    monkeypatch.setattr(app, "_report_undelivered", lambda *a, **k: events.append("not delivered"))

    def inject(text, mode, t0):
        events.append(("typed", text))
        return outcome
    monkeypatch.setattr(app, "_inject_text", inject)
    monkeypatch.setattr(app, "_press_enter_key", lambda why: events.append(("enter", why)))
    frames = [np.ones(app.SAMPLE_RATE, dtype=np.int16).tobytes()]
    app._transcribe_and_inject(frames, app.SAMPLE_RATE, beeps_on=False,
                               smart_quotes=False, notify_on=False)
    return events


def test_press_enter_types_the_words_then_presses_enter(monkeypatch):
    monkeypatch.setattr(app, "_press_enter_after", False)
    events = _dictate(monkeypatch, "See you at noon, press enter",
                      prepared=lambda r: r + ". ")
    # No auto-space before Enter: it would be sent with the message.
    assert events == [("typed", "See you at noon."), ("enter", 'said "press enter"')]


def test_press_enter_alone_only_presses_enter(monkeypatch):
    monkeypatch.setattr(app, "_press_enter_after", False)
    events = _dictate(monkeypatch, "Press enter.")
    assert events == [("enter", 'said "press enter"')]


def test_no_enter_without_the_command(monkeypatch):
    monkeypatch.setattr(app, "_press_enter_after", False)
    events = _dictate(monkeypatch, "Hello there", prepared=lambda r: r + ". ")
    assert events == [("typed", "Hello there. ")]


def test_press_enter_after_each_dictation(monkeypatch):
    monkeypatch.setattr(app, "_press_enter_after", True)
    events = _dictate(monkeypatch, "Hello there", prepared=lambda r: r + ". ")
    assert events == [("typed", "Hello there."),
                      ("enter", "Press Enter after each dictation is on")]


def test_no_enter_when_the_text_did_not_arrive(monkeypatch):
    """Enter on a half-typed message would send the wrong thing."""
    monkeypatch.setattr(app, "_press_enter_after", False)
    events = _dictate(monkeypatch, "See you at noon, press enter",
                      prepared=lambda r: r + ".", outcome="partial")
    assert ("enter", 'said "press enter"') not in events
    assert "not delivered" in events


def test_press_enter_key_uses_the_output_backend_and_forgets_undo(monkeypatch):
    pressed = []

    class Backend:
        def press_keys(self, chords):
            pressed.append(chords)
            return True
    monkeypatch.setattr(app, "_output_backend", lambda: Backend())
    monkeypatch.setattr(app.time, "sleep", lambda s: None)
    app.state.last_inserted_text = "See you at noon."
    assert app._press_enter_key("test") is True
    assert pressed == [[((), "ENTER")]]
    # A sent message can't be backspaced away.
    assert app.state.last_inserted_text == ""


def test_both_typing_paths_know_the_enter_key():
    from tuxtalk import libei_ctypes
    assert app._nav_keycode("ENTER") == 28
    assert libei_ctypes._CHORD_KEYS["ENTER"] == 28


def test_setting_is_off_by_default_and_applies_live():
    assert config.Settings().press_enter_after is False
    cfg = config.Settings(press_enter_after=True)
    app._apply_cleanup_settings(cfg)
    try:
        assert app._press_enter_after is True
    finally:
        app._apply_cleanup_settings(config.Settings())
    assert app._press_enter_after is False

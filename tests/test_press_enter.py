"""Ending a dictation with "press enter" sends a real Enter (enter_command.py).

Ron, 2026-10-17: "I really like the press enter, so you can just speak."
A spoken "new line" stays Shift+Enter, which never sends a chat message.
"""
import numpy as np
import pytest

from tuxtalk import app, config, enter_command
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
    frames = [(np.ones(app.SAMPLE_RATE, dtype=np.int16) * 1000).tobytes()]
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
                      ("enter", "Send each dictation automatically is on")]


def test_a_cut_off_dictation_is_typed_but_not_sent(monkeypatch):
    """Letting go of the key after "and" means the sentence wasn't finished;
    sending half a message can't be taken back."""
    monkeypatch.setattr(app, "_press_enter_after", True)
    events = _dictate(monkeypatch, "You can go ahead and add that. And",
                      prepared=lambda r: r + ". ")
    assert events == [("typed", "You can go ahead and add that. And. ")]


def test_saying_press_enter_sends_even_after_and(monkeypatch):
    monkeypatch.setattr(app, "_press_enter_after", True)
    events = _dictate(monkeypatch, "Bring chips and, press enter",
                      prepared=lambda r: r + ".")
    assert ("enter", 'said "press enter"') in events


@pytest.mark.parametrize("text, word", [
    ("You can add that. And.", "and"),
    ("Grab the", "the"),
    ("Meet me with, um", "um"),
    ("\u201cI said and\u201d", "and"),
])
def test_cut_off_endings(text, word):
    assert enter_command.ends_unfinished(text) == word


@pytest.mark.parametrize("text", [
    "I think so.", "I'd love to.", "I like that.", "See you then.",
    "Sounds good!", "", "Command and conquer is a game.",
])
def test_whole_sentences_are_not_cut_off(text):
    assert enter_command.ends_unfinished(text) == ""


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
    assert "press_enter_after" in config.LIVE_APPLIED_KEYS
    cfg = config.Settings(press_enter_after=True)
    app._apply_cleanup_settings(cfg)
    try:
        assert app._press_enter_after is True
    finally:
        app._apply_cleanup_settings(config.Settings())
    assert app._press_enter_after is False


# --- The wait before an automatic send, and holding it (Ron, 2026-10-18) ---

class FakeTimer:
    """threading.Timer that fires only when the test says so."""
    made = []

    def __init__(self, delay, fn, args=()):
        self.delay, self.fn, self.args, self.cancelled = delay, fn, args, False
        FakeTimer.made.append(self)

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.fn(*self.args)


TYPED = []   # what the countdown fixture's _inject_text was given


@pytest.fixture
def countdown(monkeypatch):
    FakeTimer.made = []
    monkeypatch.setattr(app.threading, "Timer", FakeTimer)
    monkeypatch.setattr(app, "_press_enter_delay", 2.0)
    pressed, labels = [], []
    monkeypatch.setattr(app, "_press_enter_key", lambda why: pressed.append(why) or True)
    from tuxtalk import screen_message
    monkeypatch.setattr(screen_message, "show_over_active_window",
                        lambda text, **kw: labels.append(text))
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: "brave-browser")
    monkeypatch.setattr(app.state, "last_inserted_window", "brave-browser")
    TYPED.clear()
    monkeypatch.setattr(app, "_inject_text", lambda text, mode, t0: TYPED.append(text) or "ok")
    return pressed, labels


def test_a_send_waits_and_says_how_to_hold_it(countdown, monkeypatch):
    pressed, labels = countdown
    monkeypatch.setattr(app, "_hold_key_name", "F8")
    app._send_automatically("test")
    assert pressed == []
    assert labels == ["Sending in 2 s. Tap F8 to hold it."]
    assert FakeTimer.made[0].delay == 2.0
    FakeTimer.made[0].fire()
    assert pressed == ["test"]
    assert app.state.pending_send is None


def test_right_away_sends_at_once(countdown, monkeypatch):
    pressed, labels = countdown
    monkeypatch.setattr(app, "_press_enter_delay", 0.0)
    app._send_automatically("test")
    assert pressed == ["test"] and labels == [] and FakeTimer.made == []


def test_a_tap_of_the_toggle_key_holds_the_send(countdown):
    pressed, labels = countdown
    app._send_automatically("test")
    assert app._hold_pending_send(announce=True) is True
    FakeTimer.made[0].fire()
    assert pressed == []
    assert labels[-1] == app.HELD_SEND_NOTICE


def test_nothing_to_hold_without_a_countdown(countdown):
    assert app._hold_pending_send(announce=True) is False


def test_no_enter_into_another_window(countdown, monkeypatch):
    """Enter in whatever the user switched to could send something else."""
    pressed, _ = countdown
    app._send_automatically("test")
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: "konsole")
    FakeTimer.made[0].fire()
    assert pressed == []


def test_pressing_the_hold_key_holds_the_send_and_records(countdown, monkeypatch):
    """Holding the key dictates more onto the unsent message."""
    pressed, _ = countdown
    app._send_automatically("test")
    monkeypatch.setattr(app, "_open_input_stream", lambda idx: None)
    for name in ("_beep", "_notify", "_notify_tray_recording_state",
                 "_arm_chunker", "_pause_media_players"):
        monkeypatch.setattr(app, name, lambda *a, **k: None)
    monkeypatch.setattr(app, "recording_indicator", None)
    try:
        assert app.start_recording(False, False, 0) is True
        assert app.state.held_send is True
        FakeTimer.made[0].fire()
        assert pressed == []
    finally:
        app.state.is_recording = False
        app.state.stream = None


def test_a_tap_too_short_to_dictate_says_not_sent(countdown, monkeypatch):
    _, labels = countdown
    reasons = []
    monkeypatch.setattr(app, "cancel_recording",
                        lambda beeps, notify, reason="": reasons.append(reason))
    monkeypatch.setattr(app.state, "held_send", True)
    monkeypatch.setattr(app.state, "silence", None)
    monkeypatch.setattr(app.state, "press_t0", app.time.time())
    assert app._finish_capture(False, False) is None
    assert reasons == [app.HELD_SEND_NOTICE]
    assert labels == [app.HELD_SEND_NOTICE]


def test_a_new_send_replaces_one_still_counting(countdown):
    pressed, _ = countdown
    app._send_automatically("first")
    app._send_automatically("second")
    assert FakeTimer.made[0].cancelled
    FakeTimer.made[1].fire()
    assert pressed == ["second"]


def test_saying_press_enter_never_waits(monkeypatch):
    monkeypatch.setattr(app, "_press_enter_after", True)
    monkeypatch.setattr(app, "_press_enter_delay", 3.0)
    events = _dictate(monkeypatch, "See you at noon, press enter",
                      prepared=lambda r: r + ". ")
    assert events[-1] == ("enter", 'said "press enter"')


def test_the_wait_is_a_setting_applied_live():
    assert config.Settings().press_enter_delay == 2.0
    assert "press_enter_delay" in config.LIVE_APPLIED_KEYS
    app._apply_cleanup_settings(config.Settings(press_enter_delay=3.0, hotkey="F7"))
    try:
        assert app._press_enter_delay == 3.0 and app._hold_key_name == "F7"
    finally:
        app._apply_cleanup_settings(config.Settings())


def test_a_held_send_types_the_space_it_left_off(countdown, monkeypatch):
    """Ron, 2026-10-18: held a send, kept talking, got "delay.All right"."""
    monkeypatch.setattr(app.state, "last_inserted_text", "Testing the delay.")
    app._send_automatically("test", " ", "type")
    app._hold_pending_send(announce=True)
    assert TYPED == [" "]
    # Undo still sees the whole dictation, space included.
    assert app.state.last_inserted_text == "Testing the delay. "


def test_a_sent_message_never_gets_the_space(countdown):
    pressed, _ = countdown
    app._send_automatically("test", " ", "type")
    FakeTimer.made[0].fire()
    assert pressed == ["test"] and TYPED == []


def test_no_space_into_another_window(countdown, monkeypatch):
    app._send_automatically("test", " ", "type")
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: "konsole")
    app._hold_pending_send(announce=True)
    assert TYPED == []


def test_the_dictation_hands_its_left_off_space_to_the_send(monkeypatch):
    monkeypatch.setattr(app, "_press_enter_after", True)
    sends = []
    monkeypatch.setattr(app, "_send_automatically",
                        lambda why, space="", mode="type": sends.append(space))
    events = _dictate(monkeypatch, "Hello there", prepared=lambda r: r + ". ")
    assert ("typed", "Hello there.") in events
    assert sends == [" "]

"""What a dictation that only partly arrives leaves behind.

Two things have to stay true when injection stops partway: nothing may be
typed that the user didn't dictate (a plain Enter in a terminal runs the
half-dictated command), and the undo buffer may never be longer than what
is really in the document, or "undo that" deletes the user's own writing.
"""

import pytest

from tuxtalk import app

MARKER = "\xa7SHIFT_ENTER\xa7"


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(app.time, "sleep", lambda s: None)
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    app.state.last_inserted_text = ""
    yield
    app.state.last_inserted_text = ""


# --- typing stops at the first failure ---------------------------------------

def test_typing_stops_at_the_first_part_that_fails(monkeypatch, quiet):
    """Typing on after a failed line ran the later lines into the earlier ones."""
    typed = []
    monkeypatch.setattr(app, "_type_text_raw", lambda t: typed.append(t) or t != "two")
    monkeypatch.setattr(app, "_send_shift_enter", lambda: True)

    assert app._type_text(MARKER.join(["one", "two", "three"])) is False
    assert typed == ["one", "two"]


def test_typing_stops_when_a_line_break_fails(monkeypatch, quiet):
    typed = []
    monkeypatch.setattr(app, "_type_text_raw", lambda t: typed.append(t) or True)
    monkeypatch.setattr(app, "_send_enter", lambda: False)

    assert app._type_text("one\ntwo") is False
    assert typed == ["one"]


# --- a terminal's paste falling back to typing --------------------------------

def test_terminal_remainder_never_presses_a_plain_enter(monkeypatch, quiet):
    """A terminal gets one paste with real newlines. When that paste failed, the
    remainder was typed with each newline as Enter, running the command."""
    monkeypatch.setattr(app, "_determine_injection_method", lambda m: ("paste", "test"))
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: "konsole")
    monkeypatch.setattr(app, "_paste_text", lambda t: False)
    monkeypatch.setattr(app, "_type_text_raw", lambda t: True)
    enters, shift_enters = [], []
    monkeypatch.setattr(app, "_send_enter", lambda: enters.append(1) or True)
    monkeypatch.setattr(app, "_send_shift_enter", lambda: shift_enters.append(1) or True)

    outcome = app._inject_text(f"ls{MARKER}foo", "auto", 0.0)

    assert outcome == "ok"
    assert enters == [], "a plain Enter was pressed in a terminal"
    assert shift_enters == [1]


def test_auto_mode_types_on_x11(monkeypatch, quiet):
    """Paste can't work without Wayland, so auto goes straight to typing."""
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert app._determine_injection_method("auto")[0] == "type"


# --- the undo buffer after a partial failure ----------------------------------

def test_failed_typing_empties_the_undo_buffer(monkeypatch, quiet):
    monkeypatch.setattr(app, "_determine_injection_method", lambda m: ("type", "test"))
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: None)
    monkeypatch.setattr(app, "_type_text", lambda t: False)
    app.state.last_inserted_text = "the previous dictation"

    assert app._inject_text("a dictation that stopped partway", "type", 0.0) == "failed"
    assert app.state.last_inserted_text == ""


def test_smart_paste_records_the_line_break_that_landed(monkeypatch, quiet):
    """Part 1 and the break after it landed, then part 2's paste failed. The
    buffer left out that break, so an undo left a stray blank line behind."""
    monkeypatch.setattr(app, "_determine_injection_method", lambda m: ("paste", "test"))
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: None)
    monkeypatch.setattr(app, "_paste_text", lambda t: t == "first")
    monkeypatch.setattr(app, "_send_shift_enter", lambda: True)
    monkeypatch.setattr(app, "_type_text", lambda t: False)

    outcome = app._inject_text(f"first{MARKER}second", "paste", 0.0)

    assert outcome == "partial"
    assert app.state.last_inserted_text == "first\n"


def test_smart_paste_leaves_out_a_line_break_that_failed(monkeypatch, quiet):
    monkeypatch.setattr(app, "_determine_injection_method", lambda m: ("paste", "test"))
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: None)
    monkeypatch.setattr(app, "_paste_text", lambda t: True)
    monkeypatch.setattr(app, "_send_shift_enter", lambda: False)
    monkeypatch.setattr(app, "_type_text", lambda t: False)

    app._inject_text(f"first{MARKER}second", "paste", 0.0)

    assert app.state.last_inserted_text == "first"


def test_fast_type_records_the_line_break_that_landed(monkeypatch, quiet):
    monkeypatch.setattr(app, "_determine_injection_method", lambda m: ("paste", "test"))
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: "Claude")
    monkeypatch.setattr(app, "_type_text_fast", lambda t: t == "first")
    monkeypatch.setattr(app, "_send_shift_enter", lambda: True)

    outcome = app._inject_text(f"first{MARKER}second", "paste", 0.0)

    assert outcome == "partial"
    assert app.state.last_inserted_text == "first\n"

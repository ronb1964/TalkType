"""Transcribe a File: closing the window or opening another file never loses
a transcript without asking (Ron closed one with no question, 2026-10-15)."""
import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from tuxtalk import file_transcribe as ft  # noqa: E402


@pytest.fixture
def win(monkeypatch):
    from tuxtalk import transcribe_window as tw
    monkeypatch.setattr(Gtk, "main_quit", lambda: None)
    # Never on the desktop: the windows are built but not shown.
    monkeypatch.setattr(Gtk.Window, "show_all", lambda self: None)
    w = tw.TranscribeWindow()
    w.asked = []
    w.answer = Gtk.ResponseType.CANCEL

    def ask(title, text, buttons):
        w.asked.append((title, text, [label for label, _ in buttons]))
        return w.answer

    w._ask = ask
    yield w
    w.window.destroy()


def done(w, text="Hello there."):
    w._on_done([ft.Piece(0.0, 5.0, text)], 5.0, 1.0, False)


def test_nothing_to_lose_closes_without_asking(win):
    assert win._on_close() is False
    assert win.asked == []


def test_unsaved_text_asks_and_cancel_keeps_the_window(win):
    done(win)
    assert win._on_close() is True                 # stays open
    title, text, buttons = win.asked[0]
    assert title == "Save the text first?" and "Closing the window loses it." in text
    assert buttons == ["Cancel", "Don't Save", "Save as Text…"]


def test_dont_save_closes(win):
    done(win)
    win.answer = Gtk.ResponseType.REJECT
    assert win._on_close() is False


def test_save_then_close(win, monkeypatch):
    done(win)
    win.answer = Gtk.ResponseType.ACCEPT
    monkeypatch.setattr(win, "_save", lambda kind: setattr(win, "kept", True))
    assert win._on_close() is False


def test_a_cancelled_save_keeps_the_window(win, monkeypatch):
    done(win)
    win.answer = Gtk.ResponseType.ACCEPT
    monkeypatch.setattr(win, "_save", lambda kind: None)
    assert win._on_close() is True


def test_copied_text_still_asks(win):
    """The next copy replaces the clipboard, so a copy isn't kept."""
    done(win)
    win._on_copy(None)
    assert win._on_close() is True
    assert "You copied it, but it isn't saved to a file." in win.asked[0][1]


def test_saved_text_closes_without_asking(win):
    done(win)
    win.kept = True                    # what a successful _save sets
    assert win._on_close() is False and win.asked == []


def test_a_new_transcript_is_unsaved_again(win):
    done(win)
    win.kept = True
    done(win, "Another one.")
    win._on_close()
    assert win.asked


def test_another_file_asks_first(win):
    done(win)
    assert win._may_discard("new") is False
    assert "Opening another file replaces it." in win.asked[0][1]


def test_closing_while_transcribing_asks_to_stop(win):
    win._set_busy(True)
    assert win._on_close() is True
    assert win.asked[0][0] == "Stop transcribing?"
    win.answer = Gtk.ResponseType.ACCEPT
    assert win._on_close() is False
    assert win._cancel.is_set()

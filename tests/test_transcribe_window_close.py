"""Transcribe a File: closing the window or opening another file never loses
a transcript without asking (Ron closed one with no question, 2026-10-15)."""
import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from tuxtalk import file_transcribe as ft  # noqa: E402


@pytest.fixture
def win(monkeypatch, tmp_path):
    from tuxtalk import transcribe_window as tw
    # The last transcript is kept here, never in the real data folder.
    monkeypatch.setattr(ft, "last_path", lambda: str(tmp_path / "last-transcript.json"))
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


def done(w, text="Hello there.", kept_for_next_time=False):
    """A file finished. Keeping it for next time is off unless asked for, so
    the close question can be tested; it's on in real use."""
    if not kept_for_next_time:
        ft_remember, ft.remember = ft.remember, lambda *a: False
    try:
        w._on_done([ft.Piece(0.0, 5.0, text)], 5.0, 1.0, False)
    finally:
        if not kept_for_next_time:
            ft.remember = ft_remember


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


# --- the last transcript, kept for next time ----------------------------------

def test_a_kept_transcript_still_asks_on_close(win):
    """Ron wants the question on every close as insurance; it says the text
    is kept, so it isn't a scare. Don't Save then closes."""
    done(win, kept_for_next_time=True)
    assert win.remembered
    assert "until you transcribe another file" in win.status.get_text()
    assert win._on_close() is True
    assert "TuxTalk shows it again when you reopen this window" in win.asked[0][1]
    win.answer = Gtk.ResponseType.REJECT
    assert win._on_close() is False


def test_another_file_still_asks_about_a_kept_transcript(win):
    """Another file replaces the kept one, so that still asks."""
    done(win, kept_for_next_time=True)
    assert win._may_discard("new") is False
    assert "Opening another file replaces it." in win.asked[0][1]


def test_reopening_shows_the_last_transcript(win, monkeypatch, tmp_path):
    from tuxtalk import transcribe_window as tw
    win.path = "/videos/Cleaver Maintenance.mov"
    done(win, "The blade gets dull.", kept_for_next_time=True)
    again = tw.TranscribeWindow()
    try:
        again.recall()
        assert [p.text for p in again.pieces] == ["The blade gets dull."]
        assert again.path == "/videos/Cleaver Maintenance.mov"
        assert "Cleaver Maintenance.mov" in again.file_label.get_text()
        assert again.srt_btn.get_sensitive() and again.txt_btn.get_sensitive()
        assert again.status.get_text().startswith("Your last transcript")
    finally:
        again.window.destroy()


def test_nothing_kept_opens_empty(win):
    win.recall()
    assert win.pieces == [] and not win.srt_btn.get_sensitive()


def test_the_kept_transcript_is_private(win, tmp_path):
    import stat
    done(win, kept_for_next_time=True)
    mode = (tmp_path / "last-transcript.json").stat().st_mode
    assert stat.S_IMODE(mode) == 0o600


def test_a_broken_kept_file_is_ignored(win, tmp_path):
    (tmp_path / "last-transcript.json").write_text("{not json")
    win.recall()
    assert win.pieces == []

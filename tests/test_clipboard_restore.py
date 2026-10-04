"""Paste mode and the clipboard (GitHub issue #7).

Every paste replaced the clipboard and nothing put it back, and on KDE every
dictation was saved into Klipper's history on disk. Now dictations are always
marked sensitive (clipboard managers skip them), and with "Restore clipboard
after pasting" on, whatever the user had copied comes back after the paste.
"""
import pytest

from talktype import clipboard as cb
from talktype import config as C


class FakeClipboard:
    """The Wayland clipboard as wl-paste / wl-copy see it."""

    def __init__(self, data=b"what I copied", mime="text/plain;charset=utf-8"):
        self.data, self.mime = data, mime
        self.restores = []

    def types(self):
        if self.data is None:
            return []
        return [self.mime] + (["TEXT"] if self.mime.startswith("text/") else [])

    def read(self, mime):
        return self.data

    def write(self, data, mime):
        self.data, self.mime = data, mime
        self.restores.append((data, mime))

    def clear(self):
        self.data = None
        self.restores.append(None)


@pytest.fixture
def board(monkeypatch):
    fake = FakeClipboard()
    monkeypatch.setattr(cb, "_wl_paste_types", fake.types)
    monkeypatch.setattr(cb, "_wl_paste", fake.read)
    monkeypatch.setattr(cb, "_wl_copy_bytes", fake.write)
    monkeypatch.setattr(cb, "_wl_clear", fake.clear)
    return fake


@pytest.fixture
def keeper():
    pending = []
    k = cb.ClipboardKeeper(schedule=lambda delay, fn: pending.append(fn) or (lambda: pending.remove(fn)))
    k.pending = pending
    return k


def paste(keeper, board, text):
    """What _paste_text does around a paste: remember, paste, schedule restore."""
    keeper.before_paste()
    board.data, board.mime = text.encode(), "text/plain;charset=utf-8"
    keeper.after_paste(text)


def run_pending(keeper):
    while keeper.pending:
        keeper.pending.pop(0)()


def test_the_old_clipboard_comes_back_after_the_paste(keeper, board):
    paste(keeper, board, "dictated words")
    assert board.data == b"dictated words"          # the app can still read it...
    run_pending(keeper)
    assert board.data == b"what I copied"           # ...and then it's back


def test_something_copied_meanwhile_is_left_alone(keeper, board):
    paste(keeper, board, "dictated words")
    board.data = b"copied right after"
    run_pending(keeper)
    assert board.data == b"copied right after" and board.restores == []


def test_two_quick_dictations_restore_the_original_not_the_first(keeper, board):
    paste(keeper, board, "first")
    paste(keeper, board, "second")                  # before the first restore ran
    run_pending(keeper)
    assert board.data == b"what I copied" and len(board.restores) == 1


def test_an_empty_clipboard_stays_empty(keeper, board):
    board.data = None
    paste(keeper, board, "dictated words")
    run_pending(keeper)
    assert board.data is None and board.restores == [None]


def test_an_image_on_the_clipboard_comes_back_as_an_image(keeper, board):
    board.data, board.mime = b"\x89PNG...", "image/png"
    paste(keeper, board, "dictated words")
    run_pending(keeper)
    assert (board.data, board.mime) == (b"\x89PNG...", "image/png")


def test_text_is_preferred_when_the_clipboard_offers_several_types(monkeypatch):
    monkeypatch.setattr(cb, "_wl_paste_types",
                        lambda: ["image/png", "text/html", "text/plain;charset=utf-8", "TEXT"])
    assert cb._best_type(cb._wl_paste_types()) == "text/plain;charset=utf-8"


def test_a_clipboard_that_cannot_be_read_is_not_touched(keeper, board, monkeypatch):
    def broken(mime):
        raise OSError("wl-paste timed out")
    monkeypatch.setattr(cb, "_wl_paste", broken)
    paste(keeper, board, "dictated words")
    run_pending(keeper)
    assert board.restores == []


# --- marking dictations sensitive --------------------------------------------------

def test_dictations_are_marked_sensitive_when_wl_copy_can(monkeypatch):
    monkeypatch.setattr(cb, "_wl_copy_help", lambda: "  --sensitive  Hint that the content is sensitive.")
    cb._sensitive_supported.cache_clear()
    assert cb.wl_copy_command() == ["wl-copy", "--sensitive"]


def test_an_older_wl_copy_still_pastes_without_the_hint(monkeypatch):
    monkeypatch.setattr(cb, "_wl_copy_help", lambda: "  -t, --type mime/type  Override the MIME type")
    cb._sensitive_supported.cache_clear()
    assert cb.wl_copy_command() == ["wl-copy"]


# --- the setting -----------------------------------------------------------------------

def test_restoring_is_off_unless_asked_for():
    """Ron re-pastes a dictation that landed in the wrong window from the
    clipboard; restoring by default would take that away."""
    assert C.Settings().restore_clipboard is False


def test_the_setting_applies_without_a_restart():
    assert "restore_clipboard" in C.LIVE_APPLIED_KEYS
    assert not C.needs_service_restart({"restore_clipboard"})


def test_paste_uses_the_keeper_only_when_the_setting_is_on(monkeypatch):
    from talktype import app
    events = []

    class Keeper:
        def before_paste(self): events.append("save")
        def after_paste(self, text): events.append(("restore", text))

    class Pipe:
        def write(self, data): pass
        def close(self): pass

    class Proc:
        returncode = 0
        stdin = Pipe()
        def poll(self): return 0
        def communicate(self, *a, **k): return b"", b""
        def wait(self, *a, **k): return 0
        def terminate(self): pass
        def kill(self): pass

    commands = []
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setattr(app, "_which", lambda name: True)
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: "kwrite")
    monkeypatch.setattr(app, "_ydotool_key", lambda keys, **kw: True)
    monkeypatch.setattr(app.subprocess, "Popen", lambda cmd, **kw: commands.append(cmd) or Proc())
    monkeypatch.setattr(app.time, "sleep", lambda s: None)
    monkeypatch.setattr(cb, "wl_copy_command", lambda: ["wl-copy", "--sensitive"])
    monkeypatch.setattr(app, "_clipboard_keeper", Keeper())

    monkeypatch.setattr(app, "_restore_clipboard", False)
    assert app._paste_text("hello") is True
    assert events == [] and commands[-1] == ["wl-copy", "--sensitive"]

    monkeypatch.setattr(app, "_restore_clipboard", True)
    assert app._paste_text("hello") is True
    assert events == ["save", ("restore", "hello")]

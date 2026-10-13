"""Tests for text injection reporting its real outcome.

Injection is the last step of every dictation. When it silently claims success
it causes the two worst failure modes this app has:

  * the wrong text lands in the document (a stale clipboard gets pasted)
  * the undo buffer records text the document never received, so a later
    "undo that" backspaces over the user's own writing

Every path here must return whether text actually reached the focused app.
"""

import subprocess

import pytest

from tuxtalk import app


class FakeCompleted:
    """Stands in for subprocess.CompletedProcess."""

    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stdout = ""
        self.stderr = stderr


class FakePopen:
    """Stands in for a wl-copy process.

    wl-copy forks by default: the process we spawn exits 0 once the clipboard
    is set, and non-zero when it cannot reach the compositor. returncode=None
    is one that never gets that far.
    """

    def __init__(self, returncode=None):
        self._returncode = returncode
        self.stdin = _FakeStdin()
        self.stderr = _FakeStderr()
        self.terminated = False

    def poll(self):
        return self._returncode

    def terminate(self):
        self.terminated = True
        if self._returncode is None:
            self._returncode = -15

    def wait(self, timeout=None):
        if self._returncode is None:
            raise subprocess.TimeoutExpired(cmd="wl-copy", timeout=timeout)
        return self._returncode


class _FakeStderr:
    def read(self):
        return b"Failed to connect to a Wayland server"

    def close(self):
        pass


class _FakeStdin:
    def __init__(self):
        self.written = b""

    def write(self, data):
        self.written += data

    def close(self):
        pass


@pytest.fixture
def wayland(monkeypatch):
    """A working Wayland session with both tools present."""
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setattr(app, "_which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: None)
    monkeypatch.setattr(app.time, "sleep", lambda s: None)


# --- the paste path must report its real outcome ---------------------------

def test_paste_reports_failure_when_the_keystroke_tool_is_down(monkeypatch, wayland):
    """ydotool exits 2 with "Please check if ydotoold is running".

    Discarding that result would report a paste that never happened as
    success, and the undo buffer would record text the document never got.
    """
    monkeypatch.setattr(app.subprocess, "Popen", lambda *a, **k: FakePopen(returncode=0))
    monkeypatch.setattr(app.subprocess, "run",
                        lambda *a, **k: FakeCompleted(returncode=2, stderr="ydotoold not running"))

    assert app._paste_text("hello") is False


def test_paste_reports_failure_when_the_clipboard_tool_dies(monkeypatch, wayland):
    """If wl-copy can't reach the compositor the clipboard was never set —
    pressing Ctrl+V then pastes whatever the user had copied earlier."""
    monkeypatch.setattr(app.subprocess, "Popen", lambda *a, **k: FakePopen(returncode=1))
    monkeypatch.setattr(app.subprocess, "run", lambda *a, **k: FakeCompleted(returncode=0))

    assert app._paste_text("hello") is False


def test_paste_reports_success_when_both_tools_succeed(monkeypatch, wayland):
    monkeypatch.setattr(app.subprocess, "Popen", lambda *a, **k: FakePopen(returncode=0))
    monkeypatch.setattr(app.subprocess, "run", lambda *a, **k: FakeCompleted(returncode=0))

    assert app._paste_text("hello") is True


def test_paste_waits_for_wl_copy_to_set_the_clipboard(monkeypatch, wayland):
    """The wl-copy we start exits once the clipboard is set. One still running
    has not got that far, so Ctrl+V would paste the old clipboard contents,
    and killing it afterwards would stop it before it could serve the new one."""
    proc = FakePopen(returncode=None)
    monkeypatch.setattr(app.subprocess, "Popen", lambda *a, **k: proc)
    keys = []
    monkeypatch.setattr(app.subprocess, "run", lambda *a, **k: keys.append(a) or FakeCompleted(returncode=0))

    assert app._paste_text("hello") is False
    assert not keys, "pasted before the clipboard held the dictation"
    assert proc.terminated, "a stuck wl-copy was left running"


def test_a_wl_copy_that_handed_off_is_not_killed(monkeypatch, wayland):
    proc = FakePopen(returncode=0)
    monkeypatch.setattr(app.subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(app.subprocess, "run", lambda *a, **k: FakeCompleted(returncode=0))

    assert app._paste_text("hello") is True
    assert not proc.terminated


def test_paste_is_refused_outside_a_wayland_session(monkeypatch):
    """On an X11 login the clipboard tool fails instantly, and sending Ctrl+V
    anyway would paste the user's previous clipboard contents into their document."""
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(app, "_which", lambda name: f"/usr/bin/{name}")
    fired = []
    monkeypatch.setattr(app.subprocess, "run", lambda *a, **k: fired.append(a) or FakeCompleted(0))

    assert app._paste_text("hello") is False
    assert not fired, "sent a paste keystroke on a session where the clipboard was never set"


def test_paste_times_out_rather_than_hanging(monkeypatch, wayland):
    """A wedged keystroke daemon must not block the thread that polls hotkeys."""
    monkeypatch.setattr(app.subprocess, "Popen", lambda *a, **k: FakePopen(returncode=0))

    def hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ydotool", timeout=kwargs.get("timeout", 5))

    monkeypatch.setattr(app.subprocess, "run", hang)

    assert app._paste_text("hello") is False


def test_every_keystroke_call_passes_a_timeout(monkeypatch, wayland):
    seen = []

    def record(*args, **kwargs):
        seen.append(kwargs.get("timeout"))
        return FakeCompleted(returncode=0)

    monkeypatch.setattr(app.subprocess, "Popen", lambda *a, **k: FakePopen(returncode=0))
    monkeypatch.setattr(app.subprocess, "run", record)

    app._paste_text("hello")
    app._send_shift_enter()
    app._send_enter()
    app._send_backspaces(3)

    assert seen, "no subprocess calls were made"
    assert all(t is not None for t in seen), f"a keystroke call had no timeout: {seen}"


# --- backspaces must report whether they landed ----------------------------

def test_send_backspaces_reports_failure_when_the_tool_fails(monkeypatch, wayland):
    monkeypatch.setattr(app.subprocess, "run", lambda *a, **k: FakeCompleted(returncode=2))

    assert app._send_backspaces(5) is False


def test_send_backspaces_reports_success(monkeypatch, wayland):
    monkeypatch.setattr(app.subprocess, "run", lambda *a, **k: FakeCompleted(returncode=0))

    assert app._send_backspaces(5) is True


# --- partial injection must not re-send what already landed ----------------

def test_failed_chunk_only_retypes_the_remainder(monkeypatch, wayland):
    """A multi-line dictation whose third chunk fails must not fall back to
    re-injecting the *entire* text, which leaves the document with the first
    chunks followed by a complete second copy of everything."""
    typed = []
    pasted = []

    def fake_paste(part, *args, **kwargs):
        pasted.append(part)
        return part != "third"  # third chunk fails

    monkeypatch.setattr(app, "_paste_text", fake_paste)
    monkeypatch.setattr(app, "_type_text", lambda t: typed.append(t) or True)
    monkeypatch.setattr(app, "_send_shift_enter", lambda: True)
    monkeypatch.setattr(app, "_determine_injection_method", lambda m: ("paste", "test"))
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: None)

    marker = "\xa7SHIFT_ENTER\xa7"
    text = marker.join(["first", "second", "third", "fourth"])
    app._inject_text(text, "paste", 0.0)

    assert typed, "nothing was retyped after the failure"
    retyped = "".join(typed)
    assert "first" not in retyped, f"re-injected a chunk that already landed: {retyped!r}"
    assert "second" not in retyped, f"re-injected a chunk that already landed: {retyped!r}"
    assert "third" in retyped, "the failed chunk was dropped"
    assert "fourth" in retyped, "the remaining chunk was dropped"


def test_undo_buffer_records_only_what_actually_landed(monkeypatch, wayland):
    """The buffer must match the document, or the next undo deletes the user's
    own writing. A failed typing run may have typed part of the text before it
    stopped, so neither this dictation nor the previous one is a safe length
    to delete: the buffer is emptied, and undo then deletes nothing."""
    monkeypatch.setattr(app, "_paste_text", lambda *a, **k: False)
    monkeypatch.setattr(app, "_type_text", lambda t: False)
    monkeypatch.setattr(app, "_determine_injection_method", lambda m: ("paste", "test"))
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: None)
    app.state.last_inserted_text = "previous dictation"

    app._inject_text("brand new text", "paste", 0.0)

    assert app.state.last_inserted_text == "", \
        "undo buffer kept a length that no longer matches the document"


def test_undo_buffer_updates_on_a_successful_injection(monkeypatch, wayland):
    monkeypatch.setattr(app, "_paste_text", lambda *a, **k: True)
    monkeypatch.setattr(app, "_determine_injection_method", lambda m: ("paste", "test"))
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: None)
    app.state.last_inserted_text = "previous"

    app._inject_text("brand new text", "paste", 0.0)

    assert app.state.last_inserted_text == "brand new text"


# --- undo must confirm the deletion before shrinking its buffer ------------

@pytest.fixture
def undo_env(monkeypatch):
    monkeypatch.setattr(app, "_beep", lambda *a, **k: None)
    monkeypatch.setattr(app, "_notify", lambda *a, **k: None)
    app.state.last_inserted_text = "hello world"
    app.state.continue_mid_sentence = False
    yield
    app.state.last_inserted_text = ""


def test_undo_leaves_its_buffer_alone_when_the_backspaces_fail(monkeypatch, undo_env):
    """Otherwise TuxTalk reports a successful undo, nothing is deleted, and the
    next undo deletes that many characters of the user's own writing."""
    monkeypatch.setattr(app, "_send_backspaces", lambda count: False)

    app._handle_undo("undo last word", beeps_on=False, notify_on=False)

    assert app.state.last_inserted_text == "hello world"


def test_undo_shrinks_its_buffer_when_the_backspaces_land(monkeypatch, undo_env):
    monkeypatch.setattr(app, "_send_backspaces", lambda count: True)

    app._handle_undo("undo last word", beeps_on=False, notify_on=False)

    assert app.state.last_inserted_text == "hello "


# --- line breaks are part of the text, and part of the report ---------------

def test_type_text_reports_failure_when_the_enter_key_fails(monkeypatch):
    """A dictation containing "new line" is typed in parts with an Enter key
    between them, so _type_text must check what _send_enter() returns as well
    as the text parts.

    Otherwise the undo buffer records one more character than the document
    actually received per failed break, and "undo that" backspaces that far
    past the dictation — into text the user typed themselves.
    """
    monkeypatch.setattr(app, "_type_text_raw", lambda t: True)
    monkeypatch.setattr(app, "_send_enter", lambda: False)

    assert app._type_text("hello\nworld") is False


def test_type_text_reports_failure_when_the_shift_enter_key_fails(monkeypatch):
    monkeypatch.setattr(app, "_type_text_raw", lambda t: True)
    monkeypatch.setattr(app, "_send_shift_enter", lambda: False)

    assert app._type_text("hello§SHIFT_ENTER§world") is False


def test_type_text_reports_success_when_every_part_lands(monkeypatch):
    monkeypatch.setattr(app, "_type_text_raw", lambda t: True)
    monkeypatch.setattr(app, "_send_enter", lambda: True)

    assert app._type_text("hello\nworld") is True


def test_type_text_still_reports_failure_when_a_text_part_fails(monkeypatch):
    monkeypatch.setattr(app, "_type_text_raw", lambda t: False)
    monkeypatch.setattr(app, "_send_enter", lambda: True)

    assert app._type_text("hello\nworld") is False


def test_injection_method_forces_type_in_flatpak(monkeypatch):
    """Inside a Flatpak there is no wl-copy, and libei types directly — so the
    method must be 'type', never 'paste', regardless of the configured mode."""
    from tuxtalk import app
    monkeypatch.setenv("FLATPAK_ID", "io.github.ronb1964.TalkType")
    for mode in ("auto", "paste", "type"):
        actual, _reason = app._determine_injection_method(mode)
        assert actual == "type", mode


def test_injection_method_respects_user_choice_on_host(monkeypatch):
    from tuxtalk import app
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    assert app._determine_injection_method("paste")[0] == "paste"
    assert app._determine_injection_method("type")[0] == "type"


def test_auto_mode_pastes_without_scanning_processes(monkeypatch):
    """Auto always pastes, so the answer must not cost a pgrep over every
    process on each dictation."""
    from tuxtalk import app
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

    def no_subprocess(*a, **k):
        raise AssertionError("auto mode must not start a process")
    monkeypatch.setattr(app.subprocess, "run", no_subprocess)

    assert app._determine_injection_method("auto")[0] == "paste"

"""Typing and undo time limits must grow with the amount of text.

`ydotool type -d D -H D` spends about two delays on every character, and
`ydotool key` waits its delay after every key event. A fixed limit cut long
dictations off partway (about 830 characters at the default 12 ms) and killed
long undos after most of the backspaces had landed.
"""

import subprocess

from tuxtalk import app


class _FakeTypeProc:
    """A `ydotool type` process that records the limit it was given."""

    def __init__(self, seen, *args, **kwargs):
        self._seen = seen
        self.returncode = 0

    def communicate(self, input=None, timeout=None):
        self._seen.append(timeout)
        return b"", b""

    def kill(self):
        pass


def _ydotool_only(monkeypatch):
    monkeypatch.setattr(app, "_which", lambda name: "/usr/bin/ydotool" if name == "ydotool" else None)
    # Plain US layout: `ydotool type`, not the per-layout key path.
    monkeypatch.setattr(app, "_type_on_layout", lambda *a, **k: None)


def test_long_dictation_gets_enough_time_to_type(monkeypatch):
    _ydotool_only(monkeypatch)
    monkeypatch.setattr(app, "_typing_delay", 12)
    seen = []
    monkeypatch.setattr(app.subprocess, "Popen", lambda *a, **k: _FakeTypeProc(seen))

    text = "word " * 400          # 2000 characters, about two minutes of speech
    assert app._type_text_raw(text) is True

    needed = len(text) * 2 * 12 / 1000
    assert seen and seen[0] > needed, f"limit {seen[0]}s is shorter than the {needed:.0f}s typing takes"


def test_slowest_typing_speed_also_gets_enough_time(monkeypatch):
    _ydotool_only(monkeypatch)
    monkeypatch.setattr(app, "_typing_delay", 50)
    seen = []
    monkeypatch.setattr(app.subprocess, "Popen", lambda *a, **k: _FakeTypeProc(seen))

    text = "x" * 500
    app._type_text_raw(text)

    assert seen[0] > len(text) * 2 * 50 / 1000


def test_fast_type_limit_grows_with_the_text(monkeypatch):
    _ydotool_only(monkeypatch)
    seen = []
    monkeypatch.setattr(app.subprocess, "Popen", lambda *a, **k: _FakeTypeProc(seen))

    app._type_text_fast("y" * 10000, delay_ms=2)

    assert seen[0] > 10000 * 2 * 2 / 1000


def test_long_undo_gets_enough_time_for_every_backspace(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("timeout")))

        class Done:
            returncode = 0
            stderr = ""
        return Done()

    monkeypatch.setattr(app, "_which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(app.subprocess, "run", fake_run)

    assert app._send_backspaces(300) is True

    cmd, timeout = calls[0]
    # The delay is set explicitly, so the limit can't drift from ydotool's speed.
    assert cmd[2:4] == ["-d", str(app.BACKSPACE_DELAY_MS)]
    assert timeout >= 300 * 2 * app.BACKSPACE_DELAY_MS / 1000


def test_backspaces_cut_off_by_the_limit_are_reported_as_partway(monkeypatch):
    monkeypatch.setattr(app, "_which", lambda name: f"/usr/bin/{name}")

    def hang(*a, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ydotool", timeout=kwargs.get("timeout"))

    monkeypatch.setattr(app.subprocess, "run", hang)

    try:
        app._send_backspaces(50)
    except app.KeystrokesStoppedPartway:
        pass
    else:
        raise AssertionError("a timed-out undo was reported as a clean failure")


def test_an_undo_stopped_partway_forgets_the_buffer(monkeypatch):
    """Most of the text may be gone already. Keeping the buffer made the next
    undo backspace that many characters again, into the user's own writing."""
    monkeypatch.setattr(app, "_beep", lambda *a, **k: None)
    monkeypatch.setattr(app, "_notify", lambda *a, **k: None)

    def partway(count):
        raise app.KeystrokesStoppedPartway("backspaces")

    monkeypatch.setattr(app, "_send_backspaces", partway)
    app.state.last_inserted_text = "a long dictation that was being undone"
    try:
        assert app._handle_undo("undo last sentence", beeps_on=False, notify_on=False) is True
        assert app.state.last_inserted_text == ""
    finally:
        app.state.last_inserted_text = ""

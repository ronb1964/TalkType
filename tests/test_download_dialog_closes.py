"""The model download window closes on every path, including the fallback.

When Hugging Face's file list can't be fetched, a Whisper model is loaded
through WhisperModel() instead. The window must still close then, rather than
sit at 50% until the user presses Cancel, which throws the finished model away.
"""
import sys
import threading
import types

import pytest

pytest.importorskip("gi")
from tuxtalk import model_helper as mh  # noqa: E402


class _Anything:
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: _Anything()


class _FakeDialog(_Anything):
    """run() waits for response(), like Gtk.Dialog; gives up as a Cancel."""

    def __init__(self, *args, **kwargs):
        self._answer = threading.Event()
        self._response = None

    def response(self, value):
        self._response = value
        self._answer.set()

    def run(self):
        if not self._answer.wait(5):
            return mh.Gtk.ResponseType.CANCEL
        return self._response


def test_fallback_download_closes_the_window(monkeypatch):
    loaded = object()
    fake_fw = types.ModuleType("faster_whisper")
    fake_fw.WhisperModel = lambda *a, **k: loaded
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_fw)

    def no_list(repo):
        raise OSError("rate limited")

    monkeypatch.setattr(mh, "is_model_cached_fast", lambda name: False)
    monkeypatch.setattr(mh, "_files_to_download", no_list)
    monkeypatch.setattr(mh.Gtk, "Dialog", _FakeDialog)
    for name in ("Label", "ProgressBar", "Button"):
        monkeypatch.setattr(mh.Gtk, name, _Anything)
    # Run GLib callbacks straight away, from whichever thread asks.
    monkeypatch.setattr(mh.GLib, "idle_add", lambda fn, *a: fn(*a))
    monkeypatch.setattr(mh.GLib, "timeout_add", lambda ms, fn, *a: fn(*a))

    result = mh.download_model_with_progress("small", show_confirmation=False)

    assert result is loaded

"""Escape during the "Checking Speed" spinner must not end the check early.

GtkDialog sends Escape and Alt+F4 as a delete-event even with the title-bar X
hidden, so run() came back while the worker was still timing and
run_speed_check() raised KeyError on the missing result.
"""
import threading

import pytest

pytest.importorskip("gi")
from tuxtalk import vulkan_setup_dialogs as vsd  # noqa: E402


class _Anything:
    """Accepts any widget call and returns another _Anything."""

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: _Anything()


def test_escape_is_refused_while_the_check_runs(monkeypatch):
    release = threading.Event()
    seen = {}

    class FakeDialog(_Anything):
        def __init__(self, *args, **kwargs):
            self.handlers = {}

        def connect(self, signal, handler):
            self.handlers[signal] = handler

        def run(self):
            # Escape while the worker is busy, then again once it has finished.
            handler = self.handlers["delete-event"]
            seen["while_running"] = handler(self, None)
            release.set()
            seen["thread"].join(2)
            seen["after"] = handler(self, None)

    real_thread = threading.Thread

    def make_thread(target, daemon):
        seen["thread"] = real_thread(target=target, daemon=daemon)
        return seen["thread"]

    monkeypatch.setattr(vsd.Gtk, "Dialog", FakeDialog)
    for name in ("Box", "Spinner", "Label"):
        monkeypatch.setattr(vsd.Gtk, name, _Anything)
    monkeypatch.setattr(vsd.GLib, "timeout_add", lambda *a, **k: 0)
    monkeypatch.setattr(vsd.threading, "Thread", make_thread)

    vsd._wait_dialog(None, lambda: release.wait(2))

    assert seen["while_running"] is True     # stays open: the check goes on
    assert seen["after"] is False            # closes normally once it is done


def test_an_interrupted_check_keeps_the_processor(monkeypatch):
    shown = []
    monkeypatch.setattr(vsd, "_wait_dialog", lambda parent, work: None)
    monkeypatch.setattr(vsd, "message",
                        lambda parent, kind, title, text, **k: shown.append(title))
    assert vsd.run_speed_check(None, "parakeet-v3") is False
    assert shown == ["Keeping the processor"]

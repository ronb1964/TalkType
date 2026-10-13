"""Preferences and the dictation service start as Python modules everywhere.

The launchers first looked for usr/bin/dictate and usr/bin/dictate-prefs next
to the code, but no package ever ships them (the AppImage has only
dictate-tray), so that branch never ran and its "AppImage path" comments
pointed readers the wrong way.
"""
import sys

from tuxtalk import service_launcher as sl


class _Popen:
    calls = []

    def __init__(self, argv, env=None, **_):
        _Popen.calls.append((argv, env))
        self.pid = 4242


def test_preferences_runs_the_module_and_keeps_the_callers_backend(monkeypatch):
    _Popen.calls = []
    monkeypatch.setattr(sl.subprocess, "Popen", _Popen)
    monkeypatch.setattr(sl, "dev_pythonpath", lambda: "/src:/site")
    monkeypatch.setenv("GDK_BACKEND", "wayland")
    sl.launch_preferences("updates")
    (argv, env), = _Popen.calls
    assert argv == [sys.executable, "-m", "tuxtalk.prefs", "--tab=updates"]
    assert env["PYTHONPATH"] == "/src:/site"
    assert env["GDK_BACKEND"] == "wayland"     # Preferences runs natively


def test_preferences_outside_a_checkout_inherits_pythonpath(monkeypatch):
    _Popen.calls = []
    monkeypatch.setattr(sl.subprocess, "Popen", _Popen)
    monkeypatch.setattr(sl, "dev_pythonpath", lambda: None)
    monkeypatch.setenv("PYTHONPATH", "/appimage/usr/src")
    sl.launch_preferences()
    (argv, env), = _Popen.calls
    assert argv == [sys.executable, "-m", "tuxtalk.prefs"]
    assert env["PYTHONPATH"] == "/appimage/usr/src"


def test_the_service_always_runs_the_module(monkeypatch):
    _Popen.calls = []
    monkeypatch.setattr(sl.subprocess, "Popen", _Popen)
    sl.launch_dictation_service()
    (argv, _env), = _Popen.calls
    assert argv == [sys.executable, "-m", "tuxtalk.app"]
    assert not hasattr(sl, "_dictate_script_path")

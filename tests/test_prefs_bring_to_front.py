"""A second "open Preferences" brings the open window to the front.

It used to do nothing when Preferences was already open, so a window hidden
behind a browser looked like Preferences had failed to open (2026-09-29).
"""
import inspect
import os
import signal

from talktype import prefs_ipc


def test_running_pid_reads_a_live_pid(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert prefs_ipc.running_pid() is None                 # no pidfile

    (tmp_path / "talktype-prefs.pid").write_text(str(os.getpid()))
    assert prefs_ipc.running_pid() == os.getpid()

    (tmp_path / "talktype-prefs.pid").write_text("999999999")  # stale
    assert prefs_ipc.running_pid() is None


def test_bring_to_front_passes_the_tab_through_a_request_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    sent = []
    monkeypatch.setattr(prefs_ipc.os, "kill", lambda pid, sig: sent.append((pid, sig)))

    assert prefs_ipc.bring_to_front(42, "stats") is True
    assert sent == [(42, signal.SIGUSR1)]
    assert prefs_ipc.take_tab_request() == "stats"
    assert prefs_ipc.take_tab_request() is None          # read once

    prefs_ipc.bring_to_front(42, "updates")
    prefs_ipc.bring_to_front(42)                         # plain "front" clears it
    assert prefs_ipc.take_tab_request() is None


def test_bring_to_front_reports_a_vanished_window(monkeypatch):
    def gone(pid, sig):
        raise ProcessLookupError
    monkeypatch.setattr(prefs_ipc.os, "kill", gone)
    assert prefs_ipc.bring_to_front(42) is False


def test_prefs_handles_the_signal_before_it_announces_its_pid():
    """SIGUSR1 terminates a process that doesn't handle it. The pidfile is how
    others find Preferences, so the handlers must be installed first."""
    from talktype import prefs
    src = inspect.getsource(prefs.main)
    assert src.index("unix_signal_add") < src.index("_acquire_prefs_singleton(")


def test_a_second_launch_forwards_and_exits(tmp_path, monkeypatch):
    from talktype import prefs
    pidfile = tmp_path / "talktype-prefs.pid"
    pidfile.write_text("4242")
    monkeypatch.setattr(prefs, "_PREFS_PIDFILE", str(pidfile))
    monkeypatch.setattr(prefs, "_pid_running", lambda pid: True)
    sent = []
    monkeypatch.setattr(prefs.prefs_ipc, "bring_to_front", lambda pid, tab: sent.append((pid, tab)))

    import pytest
    with pytest.raises(SystemExit):
        prefs._acquire_prefs_singleton("updates")
    assert sent == [(4242, "updates")]
    assert pidfile.read_text() == "4242"                   # the open one keeps it

"""Quit stops the typing helper (ydotoold) TuxTalk started, and no other.

Found in the 0.15.0 VM round: after Quit, the ydotoold TuxTalk had started
kept running. One run by a systemd service (Ron's machine) or by another
program may still be needed, so it must be left alone.
"""
import subprocess
import types

import pytest

from tuxtalk import uinput_helper as uh


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    return tmp_path


def test_the_ydotoold_tuxtalk_starts_is_noted(runtime, monkeypatch):
    monkeypatch.setattr(uh, "check_ydotoold_running", lambda: False)
    monkeypatch.setattr(uh.subprocess, "Popen", lambda *a, **k: types.SimpleNamespace(pid=4242))
    uh.ensure_ydotoold_running()
    assert (runtime / "tuxtalk-ydotoold.pid").read_text() == "4242"


def test_one_already_running_is_not_noted(runtime, monkeypatch):
    monkeypatch.setattr(uh, "check_ydotoold_running", lambda: True)
    uh.ensure_ydotoold_running()
    assert not (runtime / "tuxtalk-ydotoold.pid").exists()


def test_quit_stops_the_one_we_started(runtime):
    # A real process named ydotoold: a copy of sleep under that name.
    import shutil
    fake = runtime / "ydotoold"
    shutil.copy(shutil.which("sleep"), fake)
    proc = subprocess.Popen([str(fake), "30"])
    try:
        (runtime / "tuxtalk-ydotoold.pid").write_text(str(proc.pid))
        uh.stop_ydotoold_we_started()
        assert proc.wait(timeout=5) != 0             # it was stopped
        assert not (runtime / "tuxtalk-ydotoold.pid").exists()
    finally:
        if proc.poll() is None:
            proc.kill()


def test_a_reused_number_is_not_stopped(runtime):
    """The noted number now belongs to some other program: leave it alone."""
    proc = subprocess.Popen(["sleep", "30"])
    try:
        (runtime / "tuxtalk-ydotoold.pid").write_text(str(proc.pid))
        uh.stop_ydotoold_we_started()
        assert proc.poll() is None                    # still running
    finally:
        proc.kill()


def test_nothing_noted_stops_nothing(runtime, monkeypatch):
    killed = []
    monkeypatch.setattr(uh.os, "kill", lambda *a: killed.append(a))
    uh.stop_ydotoold_we_started()                     # no file: e.g. systemd's ydotoold
    (runtime / "tuxtalk-ydotoold.pid").write_text("not a number")
    uh.stop_ydotoold_we_started()
    assert killed == []

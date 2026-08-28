"""ydotool discovery deliberately accepts the AppImage's own bundled binary.

Two lookups in uinput_helper look similar and mean opposite things:

    check_ydotool_available()   any ydotool on PATH -- BUNDLED COUNTS
    find_ydotoold_path()        system paths only   -- bundled REJECTED

The asymmetry is intentional. The AppImage bundles ydotool, ydotoold, wl-copy
and wl-paste in usr/bin, and its AppRun puts that directory first on PATH, so
the bundled copies are what actually run. Nothing needs installing system-wide.

But `find_ydotoold_path()` feeds a systemd user unit, and a unit cannot point
at an AppImage mount that vanishes when the app exits -- so that one, and only
that one, sanitises PATH.

The trap: `check_ydotool_available()` was once named check_system_ydotool_installed(),
which reads like it should also be sanitising PATH. "Fixing" it to match its old
name would make the welcome screen show "ydotool not installed (required)" to
every AppImage user who has a perfectly good bundled copy, and would make
install_ydotool_with_pkexec() prompt for a package that is already there.

These tests exist so that change fails loudly instead of shipping.
"""

import subprocess

import pytest

from talktype.uinput_helper import check_ydotool_available


class _Result:
    def __init__(self, returncode, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def _fake_which(path, monkeypatch):
    """Make `which ydotool` resolve to `path`, or fail when path is None."""
    def fake_run(cmd, *args, **kwargs):
        assert cmd == ["which", "ydotool"]
        if path is None:
            return _Result(1, "")
        return _Result(0, path + "\n")

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_bundled_appimage_ydotool_counts_as_available(monkeypatch):
    """The regression guard: a bundled copy is a usable copy."""
    _fake_which("/tmp/.mount_TalkTyabc123/usr/bin/ydotool", monkeypatch)

    available, path = check_ydotool_available()

    assert available is True
    assert path == "/tmp/.mount_TalkTyabc123/usr/bin/ydotool"


def test_system_ydotool_counts_as_available(monkeypatch):
    _fake_which("/usr/bin/ydotool", monkeypatch)

    available, path = check_ydotool_available()

    assert available is True
    assert path == "/usr/bin/ydotool"


def test_reports_unavailable_when_nothing_is_on_path(monkeypatch):
    _fake_which(None, monkeypatch)

    available, path = check_ydotool_available()

    assert available is False
    assert path is None


def test_lookup_failure_is_not_fatal(monkeypatch):
    """A broken/missing `which` must degrade to "not available", never raise."""
    def boom(*args, **kwargs):
        raise OSError("which is not installed")

    monkeypatch.setattr(subprocess, "run", boom)

    assert check_ydotool_available() == (False, None)


def test_ydotoold_lookup_still_rejects_appimage_paths(monkeypatch):
    """The other half of the asymmetry must not drift into matching this one."""
    from talktype import uinput_helper

    monkeypatch.setenv("APPDIR", "/tmp/.mount_TalkTyabc123")

    def fake_run(cmd, *args, **kwargs):
        return _Result(0, "/tmp/.mount_TalkTyabc123/usr/bin/ydotoold\n")

    monkeypatch.setattr(uinput_helper.subprocess, "run", fake_run)
    monkeypatch.setattr(uinput_helper.os.path, "isfile", lambda p: False)

    assert uinput_helper.find_ydotoold_path() is None

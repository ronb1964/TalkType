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

The trap: `check_ydotool_available()` can look like it should also sanitise
PATH. "Fixing" it that way would make the welcome screen show "ydotool not
installed (required)" to every AppImage user who has a perfectly good bundled
copy, and would make install_ydotool_with_pkexec() prompt for a package that
is already there.

These tests exist so that change fails loudly instead of shipping.
"""

import subprocess

import pytest

from tuxtalk.uinput_helper import check_ydotool_available


def _fake_which(path, monkeypatch):
    """Make the PATH lookup of ydotool resolve to `path`, or fail when path is None."""
    import shutil

    def fake_which(cmd, *args, **kwargs):
        assert cmd == "ydotool" and not kwargs.get("path"), "must search the inherited PATH"
        return path

    monkeypatch.setattr(shutil, "which", fake_which)


def test_bundled_appimage_ydotool_counts_as_available(monkeypatch):
    """A bundled copy is a usable copy."""
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


def test_no_which_binary_is_needed(monkeypatch):
    """Minimal Arch installs have no `which`; the lookup must not need one."""
    def boom(*args, **kwargs):
        raise FileNotFoundError("which is not installed")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setenv("PATH", "/nonexistent")

    assert check_ydotool_available() == (False, None)


def test_ydotoold_lookup_still_rejects_appimage_paths(monkeypatch):
    """The other half of the asymmetry must not drift into matching this one."""
    from tuxtalk import uinput_helper

    monkeypatch.setenv("APPDIR", "/tmp/.mount_TalkTyabc123")
    monkeypatch.setattr(uinput_helper.shutil, "which",
                        lambda cmd, path=None: "/tmp/.mount_TalkTyabc123/usr/bin/ydotoold")

    assert uinput_helper.find_ydotoold_path() is None


def test_ydotoold_lookup_searches_only_system_folders(monkeypatch):
    from tuxtalk import uinput_helper
    seen = []
    monkeypatch.setattr(uinput_helper.shutil, "which",
                        lambda cmd, path=None: seen.append(path) or "/usr/bin/ydotoold")
    assert uinput_helper.find_ydotoold_path() == "/usr/bin/ydotoold"
    assert seen == [uinput_helper._SYSTEM_PATH]

"""Enabling the GNOME extension must persist even when the live shell can't.

On Wayland, `gnome-extensions enable` fails for a just-installed extension
because the running shell hasn't discovered it yet. The old code stopped there
and returned False, so onboarding never actually enabled the extension — a fresh
GNOME install rebooted to no tray icon (confirmed on a Fedora 50 VM). The fix
also writes the UUID straight into org.gnome.shell enabled-extensions, which the
shell reads on its next start.
"""

import types

import pytest

from talktype import desktop_detect as dd

UUID = "talktype@ronb1964.github.io"


def _fake_run(*, enable_rc, get_out, set_rc=0, get_rc=0):
    """Build a subprocess.run stand-in keyed on which gsettings/CLI call it is."""
    state = {"written": None, "set_calls": 0}

    def run(argv, capture_output=True, text=True, timeout=10):
        if argv[0] == "gnome-extensions" and argv[1] == "enable":
            return types.SimpleNamespace(returncode=enable_rc, stdout="", stderr="not found")
        if argv[:3] == ["gsettings", "get", "org.gnome.shell"]:
            if get_rc != 0:
                return types.SimpleNamespace(returncode=get_rc, stdout="", stderr="fail")
            out = state["written"] if state["written"] is not None else get_out
            return types.SimpleNamespace(returncode=0, stdout=out, stderr="")
        if argv[:3] == ["gsettings", "set", "org.gnome.shell"]:
            state["set_calls"] += 1
            # A real gsettings set only changes the stored value on success.
            if set_rc == 0:
                state["written"] = argv[4]  # the repr'd list we wrote
            return types.SimpleNamespace(returncode=set_rc, stdout="", stderr="")
        return types.SimpleNamespace(returncode=1, stdout="", stderr="")

    return run, state


def test_reads_empty_typed_array(monkeypatch):
    def run(argv, **k):
        return types.SimpleNamespace(returncode=0, stdout="@as []\n", stderr="")
    monkeypatch.setattr(dd.subprocess, "run", run)
    assert dd._read_enabled_extensions() == []


def test_reads_populated_array(monkeypatch):
    def run(argv, **k):
        return types.SimpleNamespace(returncode=0, stdout="['a@x', 'b@y']\n", stderr="")
    monkeypatch.setattr(dd.subprocess, "run", run)
    assert dd._read_enabled_extensions() == ["a@x", "b@y"]


def test_enable_persists_via_gsettings_when_live_enable_fails(monkeypatch):
    # Wayland fresh install: CLI enable fails, list starts empty.
    run, state = _fake_run(enable_rc=1, get_out="@as []")
    monkeypatch.setattr(dd.subprocess, "run", run)

    assert dd.enable_extension(UUID) is True
    assert UUID in state["written"], "UUID must be written into enabled-extensions"


def test_enable_returns_true_when_live_enable_succeeds(monkeypatch):
    run, _ = _fake_run(enable_rc=0, get_out="@as []")
    monkeypatch.setattr(dd.subprocess, "run", run)
    assert dd.enable_extension(UUID) is True


def test_enable_does_not_duplicate_existing_entry(monkeypatch):
    run, state = _fake_run(enable_rc=1, get_out=f"['{UUID}']")
    monkeypatch.setattr(dd.subprocess, "run", run)

    assert dd.enable_extension(UUID) is True
    # Never wrote, because it was already present (no set call recorded).
    assert state["written"] is None


def test_does_not_clobber_extensions_when_read_fails(monkeypatch):
    """A failed `gsettings get` must NOT trigger a write — that would overwrite
    the user's entire enabled-extensions list with only TalkType."""
    run, state = _fake_run(enable_rc=1, get_out="", get_rc=1)
    monkeypatch.setattr(dd.subprocess, "run", run)

    result = dd.enable_extension(UUID)
    assert state["set_calls"] == 0, "must not write enabled-extensions when the read failed"
    assert result is False, "neither CLI enable nor a safe gsettings write succeeded"


def test_enable_fails_when_neither_mechanism_works(monkeypatch):
    # CLI enable fails AND gsettings set fails -> genuinely could not enable.
    run, _ = _fake_run(enable_rc=1, get_out="@as []", set_rc=1)
    monkeypatch.setattr(dd.subprocess, "run", run)
    assert dd.enable_extension(UUID) is False

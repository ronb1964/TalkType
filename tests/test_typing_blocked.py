"""When typing can't work, say why and what fixes it.

A Fedora user on X11 dictated for minutes: every word was transcribed and none
reached the window. His typing permissions had been granted but his login
session predated them, so ydotoold failed with "Permission denied" until a
restart. 0.14.2 started telling users a dictation didn't arrive, but not why,
so the notice must now name the cause and the fix.
"""

import types

import pytest

from talktype import uinput_helper as U

@pytest.fixture
def host(monkeypatch):
    """A non-Flatpak host with /dev/uinput, configurable per test."""
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    real_exists = U.os.path.exists
    monkeypatch.setattr(U.os.path, "exists",
                        lambda p: True if p == "/dev/uinput" else real_exists(p))
    state = types.SimpleNamespace(writable=True, running=True,
                                  in_system=False, in_session=False)
    monkeypatch.setattr(U, "check_uinput_writable", lambda: state.writable)
    monkeypatch.setattr(U, "check_ydotoold_running", lambda: state.running)
    group = types.SimpleNamespace(gr_gid=4242, gr_mem=[])
    monkeypatch.setattr(U.grp, "getgrnam", lambda name: group)
    monkeypatch.setattr(U, "_username", lambda: "tester")
    monkeypatch.setattr(U.os, "getgroups",
                        lambda: [4242] if state.in_session else [1000])

    def apply():
        group.gr_mem = ["tester"] if state.in_system else []
    state.apply = apply
    return state


def test_granted_but_not_restarted_says_restart(host):
    host.writable, host.in_system, host.in_session = False, True, False
    host.apply()
    assert "restart your computer" in U.typing_blocked_reason().lower()


def test_never_granted_points_at_fix_typing(host):
    host.writable = False
    host.apply()
    reason = U.typing_blocked_reason()
    assert "Fix Typing Permissions" in reason and "restart" in reason.lower()


def test_helper_stopped_is_reported(host):
    host.running = False
    assert U.typing_blocked_reason() == U.TYPING_HELPER_STOPPED


def test_nothing_wrong_returns_none(host):
    assert U.typing_blocked_reason() is None


def test_flatpak_has_nothing_to_diagnose(host, monkeypatch):
    host.writable = False
    monkeypatch.setenv("FLATPAK_ID", "io.github.ronb1964.TalkType")
    assert U.typing_blocked_reason() is None


def test_no_input_group_does_not_crash(host, monkeypatch):
    host.writable = False

    def missing(name):
        raise KeyError(name)
    monkeypatch.setattr(U.grp, "getgrnam", missing)
    assert "Fix Typing Permissions" in U.typing_blocked_reason()


def test_failed_notice_names_the_cause_and_restarts_a_stopped_helper(monkeypatch):
    from talktype import app
    shown, started = [], []
    monkeypatch.setattr(app, "_notify", lambda title, body: shown.append(body))
    monkeypatch.setattr(app, "_beep", lambda *a, **k: None)
    monkeypatch.setattr(U, "typing_blocked_reason", lambda: U.TYPING_HELPER_STOPPED)
    monkeypatch.setattr(U, "ensure_ydotoold_running", lambda: started.append(True))

    app._report_undelivered("failed", beeps_on=False)

    assert started, "a stopped typing helper should be started again"
    assert shown and shown[0].startswith(U.TYPING_HELPER_STOPPED)
    assert "Recent Dictations" in shown[0]


def test_failed_notice_without_a_known_cause_is_unchanged(monkeypatch):
    from talktype import app
    shown = []
    monkeypatch.setattr(app, "_notify", lambda title, body: shown.append(body))
    monkeypatch.setattr(app, "_beep", lambda *a, **k: None)
    monkeypatch.setattr(U, "typing_blocked_reason", lambda: None)

    app._report_undelivered("failed", beeps_on=False)
    assert shown == [app._UNDELIVERED_NOTICES["failed"]]


def test_service_setup_uses_the_bundled_helper_when_the_system_has_none(monkeypatch):
    """An AppImage user without the ydotool package was told the package
    'may be incomplete'. TalkType brings its own copy, which the tray starts."""
    monkeypatch.setattr(U, "check_ydotool_available",
                        lambda: (True, "/tmp/.mount_TalkTyX/usr/bin/ydotool"))
    monkeypatch.setattr(U, "find_ydotoold_path", lambda: None)
    monkeypatch.setattr(U.shutil, "which",
                        lambda name: "/tmp/.mount_TalkTyX/usr/bin/ydotoold" if name == "ydotoold" else None)
    ok, message = U.setup_ydotoold_service()
    assert ok is True
    assert "built-in" in message
    assert "incomplete" not in message


def test_ensure_ydotoold_running_starts_it_only_when_stopped(monkeypatch):
    calls = []
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setattr(U.subprocess, "Popen", lambda args, **k: calls.append(args))
    monkeypatch.setattr(U, "check_ydotoold_running", lambda: True)
    U.ensure_ydotoold_running()
    assert calls == []
    monkeypatch.setattr(U, "check_ydotoold_running", lambda: False)
    U.ensure_ydotoold_running()
    assert calls == [["ydotoold"]]

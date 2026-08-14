"""The dictation service must be launched identically from everywhere.

Two places start it: the tray (at startup, and on "Restart Service") and
Preferences (on Apply/OK). They kept separate spawn code, and only the tray's
copy set GDK_BACKEND.

That was harmless while AppRun exported GDK_BACKEND=x11 for the whole app —
every process inherited it. Once the backend was scoped to the tray's spawn so
that dropdowns would work on Wayland, Preferences began restarting the service
with its own environment, which has no GDK_BACKEND. The service then ran on
native Wayland, where gtk_window_move() is ignored, so the recording indicator
snapped to centre no matter what indicator_position said.

The user-visible symptom pointed at the wrong subsystem entirely: "changing the
indicator position does nothing unless I quit and restart the app" — because
quitting made the *tray* launch it again, with the right backend.

Both call sites now go through launch_dictation_service(), so there is one
place that knows how to start it.
"""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src/talktype"

# Modules that start the dictation service.
LAUNCHERS = ["tray.py", "prefs.py"]


def test_service_launcher_module_exists():
    from talktype import service_launcher

    assert hasattr(service_launcher, "launch_dictation_service"), (
        "service_launcher must expose launch_dictation_service()"
    )


def test_launcher_requests_xwayland_first_with_a_fallback():
    """XWayland for indicator positioning; fallback so it still starts without it."""
    from talktype.service_launcher import build_service_env

    env = build_service_env({})
    backends = env.get("GDK_BACKEND", "").split(",")

    assert backends and backends[0] == "x11", (
        "The service must prefer XWayland or gtk_window_move() is ignored and "
        "indicator_position silently does nothing."
    )
    assert "wayland" in backends, (
        "Without a fallback the service cannot start at all on a machine with "
        "no XWayland — no dictation, to protect a cosmetic indicator position."
    )


def test_launcher_does_not_inherit_a_stale_backend(monkeypatch):
    """Preferences runs on native Wayland; its env must not leak into the service."""
    from talktype.service_launcher import build_service_env

    env = build_service_env({"GDK_BACKEND": "wayland"})
    assert env["GDK_BACKEND"].split(",")[0] == "x11", (
        "build_service_env must override an inherited GDK_BACKEND, not defer to "
        "it — Preferences now runs natively on Wayland and would otherwise hand "
        "the service the wrong backend."
    )


@pytest.mark.parametrize("module", LAUNCHERS)
def test_no_module_spawns_the_service_on_its_own(module):
    """A second hand-rolled spawn is how the two paths drifted apart."""
    text = (SRC / module).read_text()

    # Popen calls naming the service directly, outside the shared launcher.
    offenders = [
        line.strip()
        for line in text.splitlines()
        if "Popen" in line and ("talktype.app" in line or "dictate_script" in line)
    ]
    assert not offenders, (
        f"{module} spawns the dictation service directly ({offenders}). Use "
        f"service_launcher.launch_dictation_service() so every launch path sets "
        f"the same environment."
    )


@pytest.mark.parametrize("module", LAUNCHERS)
def test_every_launcher_uses_the_shared_helper(module):
    text = (SRC / module).read_text()
    assert "launch_dictation_service" in text, (
        f"{module} starts the dictation service but does not use the shared "
        f"launcher, so its environment can drift from the other call site."
    )

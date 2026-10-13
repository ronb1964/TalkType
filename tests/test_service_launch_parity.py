"""The dictation service must be launched identically from everywhere.

Two places start it: the tray (at startup, and on "Restart Service") and
Preferences (on Apply/OK). Both go through launch_dictation_service(), so there
is one place that knows how to start it.

Separate spawn code drifts apart. GDK_BACKEND is scoped to the service's spawn
so that dropdowns work on Wayland; a service started without it runs on native
Wayland, where gtk_window_move() is ignored, and the recording indicator snaps
to centre no matter what indicator_position says. The symptom then points at
the wrong subsystem: "changing the indicator position does nothing unless I
quit and restart the app".
"""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src/tuxtalk"

# Modules that start the dictation service.
LAUNCHERS = ["tray.py", "prefs.py"]


def test_service_launcher_module_exists():
    from tuxtalk import service_launcher

    assert hasattr(service_launcher, "launch_dictation_service"), (
        "service_launcher must expose launch_dictation_service()"
    )


def test_launcher_requests_xwayland_first_with_a_fallback():
    """XWayland for indicator positioning; fallback so it still starts without it."""
    from tuxtalk.service_launcher import build_service_env

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
    from tuxtalk.service_launcher import build_service_env

    env = build_service_env({"GDK_BACKEND": "wayland"})
    assert env["GDK_BACKEND"].split(",")[0] == "x11", (
        "build_service_env must override an inherited GDK_BACKEND, not defer to "
        "it — Preferences now runs natively on Wayland and would otherwise hand "
        "the service the wrong backend."
    )


@pytest.mark.parametrize("module", LAUNCHERS)
def test_no_module_spawns_the_service_on_its_own(module):
    """A second hand-rolled spawn would let the two paths drift apart."""
    text = (SRC / module).read_text()

    # Popen calls naming the service directly, outside the shared launcher.
    offenders = [
        line.strip()
        for line in text.splitlines()
        if "Popen" in line and ("tuxtalk.app" in line or "dictate_script" in line)
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

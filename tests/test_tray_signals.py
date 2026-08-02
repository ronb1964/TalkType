"""Tests for the tray telling the GNOME extension about committed changes.

The tray process owns the D-Bus name the extension listens on. Change signals
emitted anywhere else never reach the extension, which is why its menu could sit
on a stale model indefinitely while the GTK tray showed the new one.
"""

import pytest

from talktype import tray


class FakeDBusService:
    def __init__(self, fail=False):
        self.model_changes = []
        self._fail = fail

    def emit_model_changed(self, model_name):
        if self._fail:
            raise RuntimeError("bus went away")
        self.model_changes.append(model_name)


class FakeTray:
    """Just enough of the tray to exercise the emit helper."""

    _emit_model_changed = tray.DictationTray._emit_model_changed

    def __init__(self, dbus_service=None):
        self.dbus_service = dbus_service


def test_model_change_is_announced_to_the_extension():
    svc = FakeDBusService()

    FakeTray(svc)._emit_model_changed("large-v3")

    assert svc.model_changes == ["large-v3"]


def test_no_dbus_service_is_not_an_error():
    """The tray runs fine on desktops with no extension attached."""
    FakeTray(None)._emit_model_changed("base")  # must not raise


def test_a_failing_bus_does_not_break_the_preset_change():
    """Announcing is best-effort — the config was already saved."""
    svc = FakeDBusService(fail=True)

    FakeTray(svc)._emit_model_changed("small")  # must not raise


# --- extension packaging ----------------------------------------------------

def test_extension_version_is_bumped_whenever_extension_js_changes():
    """The in-app updater compares only this integer.

    It sat at 5 through five rewrites of extension.js, so every GNOME user who
    had ever installed the extension was told "up to date" forever and never
    received the newer menu. This test fails the build if extension.js is
    committed at a newer revision than the last version bump.
    """
    import json
    import pathlib
    import subprocess

    root = pathlib.Path(__file__).resolve().parent.parent
    ext_dir = root / "gnome-extension" / "talktype@ronb1964.github.io"
    metadata = ext_dir / "metadata.json"
    extension_js = ext_dir / "extension.js"

    version = json.loads(metadata.read_text())["version"]

    def last_commit(path):
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", str(path)],
            cwd=root, capture_output=True, text=True,
        )
        return int(out.stdout.strip() or 0)

    js_time = last_commit(extension_js)
    meta_time = last_commit(metadata)

    if js_time and meta_time and js_time > meta_time:
        pytest.fail(
            f"extension.js was committed after metadata.json was last bumped "
            f"(version is still {version}). Bump it, or GNOME users will never "
            f"be offered the update."
        )

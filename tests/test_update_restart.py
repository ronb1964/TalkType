"""Installing an update and restarting into it.

Both update buttons used to finish with os.execv on the new AppImage:
- from Preferences (its own process), the new tray found the old one still
  holding the single-instance lock and exited, so nothing restarted;
- from the tray, the tray restarted but kept the old dictation service.
Now installing only installs, and one restart path in the tray stops the
service, quits and starts the new copy. Preferences asks the tray over D-Bus.

The first-run copy into ~/AppImages also wrote straight onto the file the
launcher and autostart point at, so a quit or reboot mid-copy left a
truncated AppImage there.
"""
import os
import pathlib
import shutil
import types

import pytest

from tuxtalk import update_checker as uc

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "tuxtalk"


@pytest.fixture
def appimages(tmp_path, monkeypatch):
    """Point ~/AppImages at a temp folder."""
    folder = tmp_path / "AppImages"
    monkeypatch.setattr(uc, "APPIMAGE_DIR", str(folder))
    monkeypatch.setattr(uc, "APPIMAGE_PATH", str(folder / "TuxTalk.AppImage"))
    monkeypatch.setattr(os, "execv", lambda *a: pytest.fail("must not exec"))
    return folder


def _download(tmp_path, data=b"new version"):
    updates = tmp_path / "updates"
    updates.mkdir()
    path = updates / "TuxTalk-v9.9.9-x86_64.AppImage"
    path.write_bytes(data)
    return str(path)


# ---- installing ---------------------------------------------------------

def test_install_puts_the_update_in_place_without_restarting(tmp_path, appimages):
    dest = appimages / "TuxTalk.AppImage"
    appimages.mkdir()
    dest.write_bytes(b"old version")

    ok, _ = uc.install_appimage_update(_download(tmp_path))

    assert ok
    assert dest.read_bytes() == b"new version"
    assert os.access(dest, os.X_OK)
    assert (appimages / ".tuxtalk_just_updated").exists()
    assert sorted(p.name for p in appimages.iterdir()) == [
        ".tuxtalk_just_updated", "TuxTalk.AppImage"]
    assert not (tmp_path / "updates").exists(), "the download was left behind"


def test_a_failed_copy_keeps_the_working_appimage(tmp_path, appimages, monkeypatch):
    dest = appimages / "TuxTalk.AppImage"
    appimages.mkdir()
    dest.write_bytes(b"old version")

    def half_copy(src, dst):
        pathlib.Path(dst).write_bytes(b"new ver")
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(shutil, "copy2", half_copy)

    ok, message = uc.install_appimage_update(_download(tmp_path))

    assert not ok and "space" in message
    assert dest.read_bytes() == b"old version"
    assert [p.name for p in appimages.iterdir()] == ["TuxTalk.AppImage"], \
        "a partial copy was left in ~/AppImages"


def test_install_refuses_when_the_disk_is_too_full(tmp_path, appimages, monkeypatch):
    monkeypatch.setattr("tuxtalk.download_utils.free_space_bytes", lambda p: 1024)
    ok, message = uc.install_appimage_update(_download(tmp_path))
    assert not ok and "disk space" in message


def test_no_update_path_execs_the_appimage():
    """execv from Preferences or a worker thread is what broke the restart."""
    for path in SRC.glob("*.py"):
        assert "os.execv(" not in path.read_text(), path.name
    assert not hasattr(uc, "install_update_and_restart")


# ---- first-run copy -----------------------------------------------------

def test_first_run_copy_is_atomic(tmp_path, appimages, monkeypatch):
    running = tmp_path / "Downloads" / "TuxTalk-v9.9.9-x86_64.AppImage"
    running.parent.mkdir()
    running.write_bytes(b"x" * 1000)
    monkeypatch.setenv("APPIMAGE", str(running))

    def half_copy(src, dst):
        pathlib.Path(dst).write_bytes(b"x" * 10)
        raise OSError("interrupted")
    monkeypatch.setattr(shutil, "copy2", half_copy)

    ok, _ = uc.copy_appimage_to_standard_location()

    assert not ok
    assert list(appimages.iterdir()) == [], \
        "a truncated AppImage was left where the launcher points"


def test_first_run_copy_succeeds(tmp_path, appimages, monkeypatch):
    running = tmp_path / "TuxTalk-v9.9.9-x86_64.AppImage"
    running.write_bytes(b"x" * 1000)
    monkeypatch.setenv("APPIMAGE", str(running))

    ok, _ = uc.copy_appimage_to_standard_location()

    dest = appimages / "TuxTalk.AppImage"
    assert ok and dest.read_bytes() == b"x" * 1000 and os.access(dest, os.X_OK)


def test_restart_now_waits_for_the_first_run_copy(monkeypatch):
    import threading
    from tuxtalk import welcome_dialog as wd
    finished = threading.Event()
    release = threading.Event()

    def copy():
        release.wait(5)
        finished.set()
    thread = threading.Thread(target=copy)
    thread.start()
    monkeypatch.setattr(wd, "_appimage_copy_thread", thread)

    release.set()
    assert wd.wait_for_appimage_copy(timeout=5)
    assert finished.is_set()


def test_first_run_copy_thread_is_not_a_daemon():
    source = (SRC / "welcome_dialog.py").read_text()
    body = source[source.index("_appimage_copy_thread = _threading.Thread("):]
    assert "daemon=False" in body[:200]
    assert "wait_for_appimage_copy()" in source


# ---- restarting ---------------------------------------------------------

def test_restart_starts_the_appimage_after_this_process_exits(tmp_path, monkeypatch):
    import subprocess
    appimage = tmp_path / "TuxTalk.AppImage"
    appimage.write_bytes(b"")
    appimage.chmod(0o755)
    started = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **k: started.append((args, k)))

    ok, _ = uc.restart_via_launcher(str(appimage))

    assert ok
    args, kwargs = started[0]
    script = args[-1]
    assert f"kill -0 {os.getpid()}" in script
    assert script.endswith(f"exec {appimage}")
    assert kwargs["start_new_session"] is True


def test_restart_refuses_a_missing_appimage(tmp_path):
    ok, _ = uc.restart_via_launcher(str(tmp_path / "gone.AppImage"))
    assert not ok


class FakeTray:
    from tuxtalk import tray as _tray
    restart_app = _tray.DictationTray.restart_app

    def __init__(self):
        self.quit = 0

    def quit_app(self, _):
        self.quit += 1


def test_tray_restart_hands_off_to_the_new_appimage(monkeypatch):
    targets = []
    monkeypatch.setattr(uc, "get_install_type", lambda: "appimage")
    monkeypatch.setattr(uc, "restart_via_launcher",
                        lambda target=None: targets.append(target) or (True, "restarting"))
    tray = FakeTray()

    assert tray.restart_app() is False  # safe to schedule with GLib.idle_add
    assert targets == [uc.APPIMAGE_PATH]
    assert tray.quit == 1, "quit_app is what stops the old dictation service"


def test_tray_restart_uses_the_package_launcher(monkeypatch):
    targets = []
    monkeypatch.setattr(uc, "get_install_type", lambda: "rpm")
    monkeypatch.setattr(uc, "restart_via_launcher",
                        lambda target=None: targets.append(target) or (True, "restarting"))
    FakeTray().restart_app()
    assert targets == [None]


def test_tray_keeps_running_when_it_cannot_restart(monkeypatch):
    from tuxtalk import tray as tray_mod
    shown = []
    monkeypatch.setattr(uc, "get_install_type", lambda: "appimage")
    monkeypatch.setattr(uc, "restart_via_launcher", lambda target=None: (False, "nope"))
    monkeypatch.setattr(tray_mod, "message_dialog", lambda **k: shown.append(k) or types.SimpleNamespace(
        format_secondary_text=lambda t: None, set_position=lambda p: None,
        set_keep_above=lambda b: None, connect=lambda *a: None, show_all=lambda: None))
    tray = FakeTray()

    tray.restart_app()

    assert tray.quit == 0
    assert shown, "the user was not told to reopen TuxTalk"


def test_tray_download_install_restarts_through_restart_app():
    source = (SRC / "tray.py").read_text()
    body = source[source.index("def download_complete():"):source.index("def _download_and_install_package")]
    assert "install_appimage_update(" in body
    assert "self.restart_app()" in body


# ---- Preferences asks the tray ------------------------------------------

def test_dbus_restart_app_reaches_the_tray():
    from tuxtalk.dbus_service import TuxTalkDBusService
    calls = []
    fake = types.SimpleNamespace(_dispatch=lambda name, *a: calls.append(name))
    TuxTalkDBusService.RestartApp(fake)
    assert calls == ["restart_app"]

    source = (SRC / "tray.py").read_text()
    instance = source[source.index("class TrayAppInstance:"):]
    assert "def restart_app(self):" in instance
    assert "self.tray.restart_app" in instance


def test_preferences_asks_the_tray_to_restart(monkeypatch):
    from tuxtalk import update_ui
    asked = []
    iface = types.SimpleNamespace(RestartApp=lambda: asked.append(True))
    monkeypatch.setattr(update_ui, "_info", lambda *a: pytest.fail("no fallback needed"))

    assert update_ui.restart_via_tray(lambda: iface) is True
    assert asked == [True]


def test_preferences_explains_when_the_tray_is_unreachable(monkeypatch):
    from tuxtalk import update_ui
    shown = []
    monkeypatch.setattr(update_ui, "_info", lambda title, msg: shown.append(msg))

    def unreachable():
        raise RuntimeError("org.freedesktop.DBus.Error.ServiceUnknown")

    assert update_ui.restart_via_tray(unreachable) is False
    assert shown and "open it" in shown[0]


def test_preferences_update_paths_use_the_tray():
    source = (SRC / "prefs.py").read_text()
    body = source[source.index("def _on_download_update_clicked"):source.index("def _on_view_release_clicked")]
    assert "install_appimage_update(" in body
    assert "update_ui.restart_via_tray()" in body
    assert "restart_callback=update_ui.restart_via_tray" in body

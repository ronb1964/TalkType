"""Fixes from the fresh review of the TuxTalk rename (2026-10-11)."""
import os

from tuxtalk import update_checker as uc


def test_menu_launcher_points_at_the_installed_appimage(tmp_path, monkeypatch):
    # First run copies the AppImage to APPIMAGE_PATH (~/AppImages/TuxTalk.AppImage);
    # the launcher it writes must start that file, not the old TalkType name.
    monkeypatch.setattr(uc, "DESKTOP_FILE_PATH", str(tmp_path / "apps" / "tuxtalk.desktop"))
    monkeypatch.setattr(uc, "APPIMAGE_PATH", str(tmp_path / "AppImages" / "TuxTalk.AppImage"))
    monkeypatch.setattr(uc, "_install_app_icon", lambda: "tuxtalk")
    monkeypatch.setattr(uc, "_refresh_desktop_menu_cache", lambda: None)
    ok, _ = uc.create_desktop_launcher()
    assert ok
    text = (tmp_path / "apps" / "tuxtalk.desktop").read_text()
    assert f"Exec={tmp_path}/AppImages/TuxTalk.AppImage\n" in text


def test_a_talktype_service_left_running_by_the_update_is_recognised():
    # 0.14.x's in-app update execs the new tray without stopping the service,
    # which keeps running as "python3 -m talktype.app" and holds the lock.
    from tuxtalk.service_launcher import is_service_argv, is_pre_rename_service_argv
    assert is_service_argv(["/tmp/.mount_x/usr/bin/python3", "-m", "talktype.app"])
    assert is_pre_rename_service_argv(["python3", "-m", "talktype.app"])
    assert not is_pre_rename_service_argv(["python3", "-m", "tuxtalk.app"])
    assert not is_service_argv(["python3", "-m", "talktype.tray"])


def test_the_tray_replaces_a_pre_rename_service_on_start():
    import pathlib
    src = (pathlib.Path(uc.__file__).parent / "tray.py").read_text()
    body = src[src.index("def _auto_start_service(self):"):]
    body = body[:body.index("\n    def ")]
    assert "pre_rename_service_pids(" in body and "stop_dictation_service(" in body

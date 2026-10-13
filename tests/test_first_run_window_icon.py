"""First-run setup windows show TuxTalk's icon, not the desktop's generic one.

KDE and GNOME find a window's icon through the .desktop file its program name
(tuxtalk for the AppImage) names. The AppImage's menu launcher is only written
by the Ready screen, so the tray writes a hidden entry first, which the Ready
screen then replaces with the real launcher.
"""
import pathlib
import re

import pytest

from tuxtalk import update_checker as uc

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(uc, "DESKTOP_FILE_PATH", str(tmp_path / "apps" / "tuxtalk.desktop"))
    monkeypatch.setattr(uc, "APPIMAGE_PATH", str(tmp_path / "AppImages" / "TuxTalk.AppImage"))
    monkeypatch.setattr(uc, "_install_app_icon", lambda: "tuxtalk")
    monkeypatch.setattr(uc, "_refresh_desktop_menu_cache", lambda: None)
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setenv("APPIMAGE", str(tmp_path / "Downloads" / "TuxTalk-v0.15.0-x86_64.AppImage"))
    return tmp_path


def test_an_appimage_without_a_launcher_gets_a_hidden_entry(home):
    assert uc.create_hidden_desktop_entry()
    text = (home / "apps" / "tuxtalk.desktop").read_text()
    assert "Icon=tuxtalk\n" in text
    assert "NoDisplay=true\n" in text          # no menu entry before setup finishes
    assert f"Exec={home}/Downloads/TuxTalk-v0.15.0-x86_64.AppImage\n" in text
    assert "Type=Application\n" in text
    # ...which doesn't count as the launcher, so the Ready screen still writes it.
    assert not uc.desktop_launcher_exists()


def test_the_ready_screen_replaces_it_with_the_real_launcher(home):
    uc.create_hidden_desktop_entry()
    ok, _ = uc.create_desktop_launcher()
    assert ok
    text = (home / "apps" / "tuxtalk.desktop").read_text()
    assert "NoDisplay" not in text
    assert uc.desktop_launcher_exists()


def test_an_existing_launcher_is_left_alone(home):
    (home / "apps").mkdir()
    (home / "apps" / "tuxtalk.desktop").write_text("[Desktop Entry]\nName=Mine\n")
    assert not uc.create_hidden_desktop_entry()
    assert (home / "apps" / "tuxtalk.desktop").read_text() == "[Desktop Entry]\nName=Mine\n"
    assert uc.desktop_launcher_exists()


@pytest.mark.parametrize("appimage,flatpak", [
    ("/opt/tuxtalk/TuxTalk.AppImage", ""),     # AUR: a user entry would hide its menu entry
    ("", "io.github.ronb1964.TuxTalk"),        # Flatpak
    ("", ""),                                  # dev checkout
])
def test_installs_with_their_own_launcher_get_nothing(home, monkeypatch, appimage, flatpak):
    monkeypatch.setenv("APPIMAGE", appimage)
    monkeypatch.setenv("FLATPAK_ID", flatpak)
    assert not uc.create_hidden_desktop_entry()
    assert not (home / "apps" / "tuxtalk.desktop").exists()


def test_a_failure_never_raises(home, monkeypatch):
    monkeypatch.setattr(uc, "DESKTOP_FILE_PATH", "/proc/nope/tuxtalk.desktop")
    assert not uc.create_hidden_desktop_entry()


def test_the_tray_writes_it_after_the_rename_and_before_any_window():
    src = (ROOT / "src" / "tuxtalk" / "tray.py").read_text()
    body = re.search(r"\ndef main\(\):\n(.*?)(?=\ndef |\nif __name__)", src, re.S).group(1)
    call = body.index("create_hidden_desktop_entry()")
    # The rename moves talktype.desktop only while tuxtalk.desktop is missing.
    assert body.index("adopt_old_install(") < call < body.index("DictationTray()")

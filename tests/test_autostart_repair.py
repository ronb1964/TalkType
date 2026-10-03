"""Repairing a login entry left pointing at a stale AppImage.

0.10.1 stopped new setups from pointing launch-at-login at the AppImage the
user happened to run setup from (usually ~/Downloads). Setups done before
that kept the old entry: on the test VM it still launched
~/Downloads/TalkType-v0.10.0-x86_64.AppImage, an old version that needs
libfuse2, so on Ubuntu 26.04 TalkType silently never started at login
(2026-10-02). The installed AppImage now repairs such an entry on startup.
"""
import pytest

from talktype import autostart, config


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path
    installed = home / "AppImages" / "TalkType.AppImage"
    installed.parent.mkdir()
    installed.write_text("")
    installed.chmod(0o755)
    entry = home / ".config" / "autostart" / "talktype.desktop"
    entry.parent.mkdir(parents=True)
    monkeypatch.setattr(autostart, "INSTALLED_APPIMAGE", str(installed))
    monkeypatch.setattr(autostart, "_autostart_desktop_path", lambda: str(entry))
    monkeypatch.setattr(config, "DEV_MODE", False)
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setenv("APPIMAGE", str(installed))
    return home, installed, entry


def _entry(path, exec_line, extra=""):
    path.write_text(f"[Desktop Entry]\nType=Application\nName=TalkType\nExec={exec_line}\n{extra}")


def test_entry_pointing_at_an_old_downloaded_appimage_is_repaired(env):
    home, installed, entry = env
    _entry(entry, str(home / "Downloads" / "TalkType-v0.10.0-x86_64.AppImage"))

    assert autostart.repair_stale_appimage_autostart() is True
    assert f"Exec={installed}\n" in entry.read_text()


def test_entry_already_on_the_installed_copy_is_left_alone(env):
    home, installed, entry = env
    _entry(entry, str(installed))
    before = entry.read_text()

    assert autostart.repair_stale_appimage_autostart() is False
    assert entry.read_text() == before


@pytest.mark.parametrize("contents", [
    "[Desktop Entry]\nType=Application\nName=TalkType\nHidden=true\n",   # turned off
    "[Desktop Entry]\nExec=/x/TalkType-v0.10.0-x86_64.AppImage\nX-GNOME-Autostart-enabled=false\n",
    "[Desktop Entry]\nExec=/usr/bin/talktype\n",                         # .deb/.rpm launcher
    "[Desktop Entry]\nExec=/home/u/Apps/SomethingElse.AppImage\n",       # not ours
])
def test_disabled_or_unrelated_entries_are_never_touched(env, contents):
    _home, _installed, entry = env
    entry.write_text(contents)

    assert autostart.repair_stale_appimage_autostart() is False
    assert entry.read_text() == contents


def test_only_the_appimage_repairs(env, monkeypatch):
    home, _installed, entry = env
    _entry(entry, str(home / "Downloads" / "TalkType-v0.10.0-x86_64.AppImage"))

    monkeypatch.delenv("APPIMAGE")                         # dev, .deb, .rpm
    assert autostart.repair_stale_appimage_autostart() is False
    monkeypatch.setenv("APPIMAGE", "/x/TalkType.AppImage")
    monkeypatch.setenv("FLATPAK_ID", "io.github.ronb1964.TalkType")
    assert autostart.repair_stale_appimage_autostart() is False


def test_no_installed_copy_means_no_repair(env):
    home, installed, entry = env
    installed.unlink()
    _entry(entry, str(home / "Downloads" / "TalkType-v0.10.0-x86_64.AppImage"))

    assert autostart.repair_stale_appimage_autostart() is False

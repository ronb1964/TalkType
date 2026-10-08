"""TalkType's windows name the launcher they belong to.

Nothing set the program name, so on Wayland every TalkType window reported
itself as "python3" and KDE showed its generic "W" icon in the title bar and
taskbar instead of TalkType's microphone. The desktop finds the icon by
matching the program name to a launcher (.desktop file), and each install
type names its launcher differently:

  AppImage   ~/.local/share/applications/talktype.desktop  (first run)
  AUR        /usr/share/applications/talktype.desktop
  deb / rpm  /usr/share/applications/io.github.ronb1964.TalkType.desktop
  Flatpak    io.github.ronb1964.TalkType
  dev        ~/.local/share/applications/talktype-dev.desktop
"""
import pathlib
import re

import pytest

from talktype import desktop_identity

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("install_type,expected", [
    ("appimage", "talktype"),
    ("aur", "talktype"),
    ("deb", "io.github.ronb1964.TalkType"),
    ("rpm", "io.github.ronb1964.TalkType"),
    ("package", "io.github.ronb1964.TalkType"),
    ("flatpak", "io.github.ronb1964.TalkType"),
    ("dev", "talktype-dev"),
])
def test_name_matches_the_launcher_of_each_install(install_type, expected):
    assert desktop_identity.desktop_id(install_type) == expected


def test_the_launchers_really_have_those_names():
    deb = (ROOT / "build-deb.sh").read_text()
    rpm = (ROOT / "build-rpm.sh").read_text()
    assert "applications/io.github.ronb1964.TalkType.desktop" in deb
    assert "applications/io.github.ronb1964.TalkType.desktop" in rpm
    assert 'install -Dm644 talktype.desktop "${pkgdir}/usr/share/applications/talktype.desktop"' \
        in (ROOT / "aur" / "PKGBUILD").read_text()
    from talktype.update_checker import DESKTOP_FILE_PATH
    assert DESKTOP_FILE_PATH.endswith("/talktype.desktop")


def test_apply_sets_the_program_name(monkeypatch):
    names = []
    monkeypatch.setattr("talktype.update_checker.get_install_type", lambda: "appimage")
    monkeypatch.setattr(desktop_identity.GLib, "set_prgname", names.append)
    desktop_identity.apply()
    assert names == ["talktype"]


def test_apply_never_raises(monkeypatch):
    def broken():
        raise RuntimeError("no idea how this is installed")
    monkeypatch.setattr("talktype.update_checker.get_install_type", broken)
    desktop_identity.apply()


@pytest.mark.parametrize("module", ["tray", "prefs", "app"])
def test_every_program_with_windows_names_itself_first(module):
    """The tray (and its dialogs), Preferences and the dictation service (the
    recording indicator) each run as their own process."""
    src = (ROOT / "src" / "talktype" / f"{module}.py").read_text()
    body = re.search(r"\ndef main\(\):\n(.*?)(?=\ndef |\nif __name__)", src, re.S).group(1)
    first_lines = [l for l in body.splitlines() if l.strip() and not l.strip().startswith("#")][:3]
    assert any("desktop_identity.apply()" in l for l in first_lines), first_lines

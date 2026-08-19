"""On the Flatpak, launch-at-login MUST go through the Background portal — a
sandboxed app writing ~/.config/autostart only reaches its private config, which
the desktop never reads, so the app would never start at login (the bug a user
hit). Off Flatpak it must still write the XDG autostart .desktop directly.
"""
from talktype import autostart


def test_set_autostart_uses_background_portal_on_flatpak(monkeypatch):
    monkeypatch.setenv("FLATPAK_ID", "io.github.ronb1964.TalkType")
    seen = []
    monkeypatch.setattr(autostart, "_set_autostart_flatpak",
                        lambda enable: seen.append(enable) or True)

    def _must_not_write_file():
        raise AssertionError("must not touch ~/.config/autostart on the Flatpak")
    monkeypatch.setattr(autostart, "_autostart_desktop_path", _must_not_write_file)

    assert autostart.set_autostart(True) is True
    assert autostart.set_autostart(False) is True
    assert seen == [True, False]


def test_set_autostart_writes_desktop_file_off_flatpak(tmp_path, monkeypatch):
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    df = tmp_path / "autostart" / "talktype.desktop"
    monkeypatch.setattr(autostart, "_autostart_desktop_path", lambda: str(df))
    monkeypatch.setattr(autostart, "get_launch_command", lambda: "/usr/bin/talktype")
    monkeypatch.setattr(autostart, "get_icon_path", lambda: "icon")

    assert autostart.set_autostart(True) is True
    assert df.exists()
    assert "Exec=/usr/bin/talktype" in df.read_text()

"""On the Flatpak, launch-at-login MUST go through the Background portal — a
sandboxed app writing ~/.config/autostart only reaches its private config, which
the desktop never reads, so the app would never start at login (the bug a user
hit). Off Flatpak it must still write the XDG autostart .desktop directly.
"""
from tuxtalk import autostart


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
    monkeypatch.setattr(autostart, "get_launch_command", lambda *a, **k: "/usr/bin/talktype")
    monkeypatch.setattr(autostart, "get_icon_path", lambda: "icon")

    assert autostart.set_autostart(True) is True
    assert df.exists()
    assert "Exec=/usr/bin/talktype" in df.read_text()


def test_a_background_portal_that_never_answers_gives_up(monkeypatch):
    """Preferences' Apply waited forever for a portal that took the request
    and never sent its Response."""
    import threading
    from tuxtalk import portal_common as pc

    class SilentBus:
        def __init__(self):
            self.subs = set()

        def get_unique_name(self):
            return ":1.9"

        def signal_subscribe(self, *args):
            self.subs.add(1)
            return 1

        def signal_unsubscribe(self, sid):
            self.subs.remove(sid)

        def call_sync(self, *args):
            pass

    bus = SilentBus()
    monkeypatch.setattr(pc, "session_bus", lambda: bus)
    monkeypatch.setattr(autostart, "_PORTAL_TIMEOUT_S", 1)
    out = []
    t = threading.Thread(target=lambda: out.append(autostart._set_autostart_flatpak(True)),
                         daemon=True)
    t.start()
    t.join(10)
    assert not t.is_alive(), "set_autostart never returned"
    assert out == [False]
    assert bus.subs == set()

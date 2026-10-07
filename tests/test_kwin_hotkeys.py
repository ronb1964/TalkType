"""KWin holds TalkType's hotkeys back from the focused app (the F8 "~" leak).

The behaviour itself was proven by hand on Plasma 6.7.4 (see the module
docstring). These pin the parts that are easy to break: which keys are claimed,
that a bare letter never is, that a changed hotkey is registered fresh, and
that nothing here can raise into the service or the tray.
"""
import types

import pytest

from talktype import kwin_hotkeys as kh


def _cfg(hotkey="F8", toggle="F9", vc="Ctrl+Alt+V"):
    return types.SimpleNamespace(hotkey=hotkey, toggle_hotkey=toggle,
                                 voice_commands_hotkey=vc)


class FakeBus:
    """Records calls; keeps a set of registered talktype-* names like KWin."""

    def __init__(self, existing=(), refuse=(), fail=()):
        self.calls = []
        self.names = list(existing)
        self.refuse = set(refuse)   # names KDE gives no key (taken elsewhere)
        self.fail = set(fail)       # methods that raise
        self.script = None

    def call(self, method, *args):
        self.calls.append((method, *args))
        if method in self.fail:
            raise RuntimeError(method)
        if method == "loadScript":
            with open(args[0]) as f:
                self.script = f.read()
            for line in self.script.splitlines():
                if line.startswith("registerShortcut("):
                    self.names.append(line.split('"')[1])
            return 7
        if method == "unloadScript":
            self.script = None
            return True
        if method == "shortcutNames":
            return list(self.names)
        if method == "unregister":
            self.names.remove(args[1])
            return True
        if method == "allShortcutInfos":
            return [(n, "", "kwin", "KWin", "default", "", [] if n in self.refuse else [1], [])
                    for n in self.names]
        return None


@pytest.fixture
def on_kde(monkeypatch, tmp_path):
    monkeypatch.setattr(kh, "should_claim", lambda: True)
    monkeypatch.setattr(kh, "script_path", lambda: str(tmp_path / "kwin" / "hk.js"))
    monkeypatch.setattr(kh.time, "sleep", lambda s: None)   # tests never really wait


class TestKeySequences:
    @pytest.mark.parametrize("name,qt", [
        ("F8", "F8"), ("f12", "F12"), (" F1 ", "F1"),
        ("Ctrl+Alt+V", "Ctrl+Alt+V"), ("ctrl+shift+h", "Ctrl+Shift+H"),
        ("Super+F5", "Meta+F5"),
    ])
    def test_translates(self, name, qt):
        assert kh.qt_key_sequence(name) == qt

    @pytest.mark.parametrize("name", ["", "   ", None, "A", "q", "F13", "Hyper+V",
                                      "Ctrl+", "Ctrl+Esc"])
    def test_refuses(self, name):
        """A bare letter would stop the user typing it anywhere."""
        assert kh.qt_key_sequence(name) is None

    def test_one_shortcut_per_key(self):
        names = [k for _n, _t, k in kh.wanted_shortcuts(_cfg("F8", "F8", ""))]
        assert names == ["F8"]

    def test_key_is_part_of_the_name(self):
        """kglobalaccel keeps a saved key over a new default, so a changed
        hotkey must come in under a new name."""
        assert kh.wanted_shortcuts(_cfg("F8"))[0][0] != kh.wanted_shortcuts(_cfg("F10"))[0][0]
        assert all(n.startswith(kh.SHORTCUT_PREFIX) for n, _t, _k in kh.wanted_shortcuts(_cfg()))


class TestScript:
    def test_registers_every_hotkey_with_a_do_nothing_callback(self):
        script = kh.build_script(kh.wanted_shortcuts(_cfg()))
        for key in ("F8", "F9", "Ctrl+Alt+V"):
            assert f'"{key}", function() {{}});' in script


class TestClaim:
    def test_loads_and_runs_the_script(self, on_kde):
        bus = FakeBus()
        assert kh.claim(_cfg(), bus) is True
        assert ("loadScript", kh.script_path(), kh.SCRIPT_PLUGIN_NAME) in bus.calls
        assert ("start",) in bus.calls
        assert not any(c[0] == "run" for c in bus.calls)
        assert sorted(bus.names) == sorted(n for n, _t, _k in kh.wanted_shortcuts(_cfg()))

    def test_a_changed_hotkey_replaces_the_old_one(self, on_kde):
        bus = FakeBus()
        kh.claim(_cfg("F8", "", ""), bus)
        kh.claim(_cfg("F10", "", ""), bus)
        assert bus.names == ["talktype-hold-F10"]

    def test_clears_leftovers_from_an_older_run(self, on_kde):
        bus = FakeBus(existing=["talktype-hold-F3", "Window Close"])
        kh.claim(_cfg("F8", "", ""), bus)
        assert sorted(bus.names) == ["Window Close", "talktype-hold-F8"]

    def test_a_key_kde_refuses_is_logged(self, on_kde, caplog):
        bus = FakeBus(refuse={"talktype-hold-F8"})
        kh.claim(_cfg("F8", "", ""), bus)
        assert "KDE already uses F8" in caplog.text

    def test_keys_kwin_is_still_registering_are_not_reported(self, on_kde, caplog, monkeypatch):
        """Restarting the service re-claims the keys within a second, and the
        first read-back can come before KWin has finished: 0.14.2's test logged
        "KDE already uses F8" while KWin really held F8, F9 and Ctrl+Alt+V."""
        waits = []
        monkeypatch.setattr(kh.time, "sleep", waits.append)
        bus = FakeBus()
        real_call, empty_reads = bus.call, [2]

        def slow_kwin(method, *args):
            result = real_call(method, *args)
            if method == "allShortcutInfos" and empty_reads[0]:
                empty_reads[0] -= 1
                return [(i[0], *i[1:6], [], i[7]) for i in result]
            return result
        bus.call = slow_kwin
        kh.claim(_cfg(), bus)
        assert "already uses" not in caplog.text
        assert len(waits) == 2

    def test_a_refused_key_is_reported_after_waiting(self, on_kde, caplog, monkeypatch):
        waits = []
        monkeypatch.setattr(kh.time, "sleep", waits.append)
        kh.claim(_cfg("F8", "", ""), FakeBus(refuse={"talktype-hold-F8"}))
        assert "KDE already uses F8" in caplog.text
        assert 0 < sum(waits) <= 1.5          # it waits a little, never long

    def test_no_keys_means_no_script(self, on_kde):
        bus = FakeBus()
        assert kh.claim(_cfg("", "", ""), bus) is False
        assert not any(c[0] == "loadScript" for c in bus.calls)

    def test_kwin_failing_is_not_fatal(self, on_kde):
        bus = FakeBus(fail={"loadScript"})
        assert kh.claim(_cfg(), bus) is False

    def test_off_kde_does_nothing(self, monkeypatch):
        monkeypatch.setattr(kh, "should_claim", lambda: False)
        bus = FakeBus()
        assert kh.claim(_cfg(), bus) is False
        assert bus.calls == []


class TestRelease:
    def test_unloads_and_forgets_only_ours(self, on_kde):
        bus = FakeBus()
        kh.claim(_cfg(), bus)
        bus.names.append("Window Close")
        kh.release(bus)
        assert ("unloadScript", kh.SCRIPT_PLUGIN_NAME) in bus.calls
        assert bus.names == ["Window Close"]

    def test_never_raises(self, on_kde):
        kh.release(FakeBus(fail={"unloadScript", "shortcutNames", "unregister"}))

    def test_no_bus_is_fine(self, on_kde):
        kh.release()   # conftest makes session_bus() raise


class TestShouldClaim:
    def test_flatpak_never_claims(self, monkeypatch):
        monkeypatch.setenv("FLATPAK_ID", "io.github.ronb1964.TalkType")
        monkeypatch.setattr(kh.desktop_detect, "get_desktop_environment", lambda: "kde")
        assert kh.should_claim() is False

    def test_only_kde(self, monkeypatch):
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        monkeypatch.setattr(kh.desktop_detect, "get_desktop_environment", lambda: "gnome")
        assert kh.should_claim() is False


def test_stopping_the_service_releases_the_hotkeys(monkeypatch):
    """SIGTERM skips the service's exit hooks, so the stop path must do it."""
    from talktype import service_launcher
    released = []
    monkeypatch.setattr(service_launcher, "find_service_pids", lambda: [])
    monkeypatch.setattr(kh, "release", lambda *a: released.append(True))
    service_launcher.stop_dictation_service()
    assert released == [True]

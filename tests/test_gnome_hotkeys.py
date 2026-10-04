"""GNOME: the extension holds TalkType's hotkeys back from the focused app.

Same leak as KDE (test_kwin_hotkeys): the service reads keys below the desktop,
so GNOME Shell also hands F8 to the app and a terminal prints "~". The service
sends its hotkeys to the tray in accelerator syntax, the tray relays them, and
the extension grabs them while the service runs. The grab itself was verified
in the ubuntu26.04 GNOME VM; these pin the Python side and the contract the
extension depends on.
"""
import pathlib
import types

import pytest

from talktype import gnome_hotkeys as gh

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXTENSION = ROOT / "gnome-extension" / "talktype@ronb1964.github.io" / "extension.js"


def _cfg(hotkey="F8", toggle="F9", vc="Ctrl+Alt+V"):
    return types.SimpleNamespace(hotkey=hotkey, toggle_hotkey=toggle,
                                 voice_commands_hotkey=vc)


class TestAccelerators:
    @pytest.mark.parametrize("qt,accel", [
        ("F8", "F8"), ("F12", "F12"),
        ("Ctrl+Alt+V", "<Control><Alt>v"),
        ("Ctrl+Shift+H", "<Control><Shift>h"),
        ("Meta+F5", "<Super>F5"),
    ])
    def test_converts(self, qt, accel):
        assert gh.accelerator(qt) == accel

    def test_the_configured_hotkeys(self):
        assert gh.accelerators(_cfg()) == ["F8", "F9", "<Control><Alt>v"]

    def test_same_rule_as_kde(self):
        """A bare letter would stop the user typing it while dictation runs."""
        assert gh.accelerators(_cfg("A", "", "")) == []

    def test_nothing_configured(self):
        assert gh.accelerators(_cfg("", "", "")) == []


class TestTheTrayRelaysThem:
    @pytest.fixture
    def svc(self):
        from talktype.dbus_service import TalkTypeDBusService
        s = TalkTypeDBusService.__new__(TalkTypeDBusService)  # no real bus
        s.claimed_hotkeys = []
        s.sent = []
        s.HotkeysChanged = lambda accels: s.sent.append(list(accels))
        return s

    def test_notify_stores_and_signals(self, svc):
        svc.NotifyClaimedHotkeys(["F8", "<Control><Alt>v"])
        assert svc.claimed_hotkeys == ["F8", "<Control><Alt>v"]
        assert svc.sent == [["F8", "<Control><Alt>v"]]

    def test_a_stopped_service_clears_them(self, svc):
        svc.NotifyClaimedHotkeys(["F8"])
        svc.clear_claimed_hotkeys()
        assert svc.claimed_hotkeys == []
        assert svc.sent[-1] == []

    def test_clearing_nothing_sends_nothing(self, svc):
        svc.clear_claimed_hotkeys()
        assert svc.sent == []


class TestTheExtensionContract:
    """String checks: the extension can't be run here, and these are the
    lines whose loss would quietly bring the leak back or strand a grab."""

    src = EXTENSION.read_text()

    def test_it_listens_for_the_signal(self):
        assert '<signal name="HotkeysChanged">' in self.src
        assert "connectSignal('HotkeysChanged'" in self.src

    def test_it_reads_them_from_status(self):
        assert "status.hotkeys" in self.src

    def test_it_only_grabs_while_the_service_runs(self):
        assert "(this._dbusAvailable && this._isServiceRunning) ? this._hotkeys : []" in self.src

    def test_destroy_ungrabs(self):
        destroy = self.src[self.src.index("    destroy() {"):]
        assert "this._ungrabHotkey(action)" in destroy

    def test_service_state_changes_resync(self):
        block = self.src[self.src.index("connectSignal('ServiceStateChanged'"):]
        block = block[:block.index("}));")]
        assert "_syncHotkeyGrabs()" in block

"""Test-suite wide setup.

Keep the suite's logging out of the user's real TalkType log. Modules create
their file handler at import time, so this has to happen before any test
module imports talktype, which is why it runs at conftest import rather than
in a fixture. Subprocesses started by tests inherit it through the
environment.
"""
import atexit
import os
import shutil
import tempfile

import pytest

_LOG_DIR = tempfile.mkdtemp(prefix="talktype-test-logs-")
os.environ["TUXTALK_LOG_DIR"] = _LOG_DIR
# Never move the real ~/.config/talktype or ~/.local/share/TalkType while the
# suite imports tuxtalk (the rename migration runs on package import).
os.environ["TUXTALK_NO_MIGRATE"] = "1"
atexit.register(shutil.rmtree, _LOG_DIR, ignore_errors=True)


def _hold_back_notifications():
    """Desktop notifications from tests must never reach the user's desktop.

    A CUDA-fallback test popped "Couldn't use your NVIDIA graphics card" on
    every suite run, all through a release test. Patched here, at conftest
    import, so it covers module-level code too; tests that check a message
    stub app._notify themselves.
    """
    try:
        import gi
        gi.require_version("Notify", "0.7")
        from gi.repository import Notify
    except Exception:
        return

    def _held_back(self, *args, **kwargs):
        return True

    Notify.Notification.show = _held_back


_hold_back_notifications()


@pytest.fixture(autouse=True)
def _no_real_kwin(monkeypatch):
    """Never let a test register or release hotkeys in the user's live KWin.

    service_launcher.stop_dictation_service() releases them, and on a KDE
    machine running the suite would hand the dev service's F8 back to whatever
    app has focus. Tests of kwin_hotkeys pass their own fake bus.
    """
    from tuxtalk import kwin_hotkeys

    def _refuse():
        raise RuntimeError("tests must not talk to the real KWin")

    monkeypatch.setattr(kwin_hotkeys, "session_bus", _refuse)


@pytest.fixture(autouse=True)
def _no_real_media_players(monkeypatch):
    """Never let a test pause the user's music.

    Tests that run the service's settings reload turn pause_media on, and later
    tests call the real start_recording. Tests of media_pause pass a fake bus.
    """
    from tuxtalk import media_pause

    def _refuse(self):
        raise RuntimeError("tests must not talk to real media players")

    monkeypatch.setattr(media_pause.SessionBus, "_bus", _refuse)


_HOTKEY_TEST_FLAG = os.path.join(_LOG_DIR, ".hotkey_test_mode")


@pytest.fixture(autouse=True)
def _no_real_hotkey_test_flag(monkeypatch):
    """Keep tests off the real hotkey test flag in the user's data folder.

    Test Hotkeys open in the real Preferences would otherwise turn every key
    press a test sends into a test-mode report. Tests of the flag write here.
    """
    import sys
    from tuxtalk import service_launcher

    monkeypatch.setattr(service_launcher, "hotkey_test_flag_path", lambda: _HOTKEY_TEST_FLAG)
    app = sys.modules.get("tuxtalk.app")
    if app is not None:
        monkeypatch.setattr(app, "_hotkey_test_flag", None)
    yield
    try:
        os.remove(_HOTKEY_TEST_FLAG)
    except OSError:
        pass

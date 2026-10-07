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
os.environ["TALKTYPE_LOG_DIR"] = _LOG_DIR
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
    from talktype import kwin_hotkeys

    def _refuse():
        raise RuntimeError("tests must not talk to the real KWin")

    monkeypatch.setattr(kwin_hotkeys, "session_bus", _refuse)

"""The tray shows notices without loading the dictation engine.

Borrowing app.py's libnotify wrapper would import app.py, which loads numpy,
faster_whisper and torch: about 300 MB that the tray would then keep for the
whole session, the first time anyone changes Text Injection Mode or picks a
Performance preset. A fresh interpreter is used because the rest of the suite
has already imported tuxtalk.app.
"""

import os
import subprocess
import sys
import textwrap

from tuxtalk import notify

SCRIPT = textwrap.dedent("""
    import sys, types
    import tuxtalk.config as config
    import tuxtalk.notify as notify
    from tuxtalk import tray

    cfg = types.SimpleNamespace(injection_mode="auto", model="small", device="cpu",
                                recommend_notice_shown=False, notify=True)
    config.load_config = lambda: cfg
    config.save_config = lambda c: None
    shown = []
    notify.notify = lambda title, body: shown.append(body)

    t = types.SimpleNamespace(dbus_service=None, _updating_injection_mode=False,
                              restart_service=lambda _: None)
    tray.DictationTray.set_injection_mode(t, "paste")

    assert shown == ["Input mode: Clipboard Paste"], shown
    for heavy in ("tuxtalk.app", "faster_whisper", "torch", "numpy"):
        assert heavy not in sys.modules, heavy + " was loaded into the tray"
    print("ok")
""")


def test_changing_injection_mode_does_not_load_the_dictation_engine():
    env = dict(os.environ)
    out = subprocess.run([sys.executable, "-c", SCRIPT], env=env,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr


def test_the_mode_confirmation_follows_the_notifications_setting(monkeypatch):
    """Mint VM test, 2026-10-13: "Input mode: Clipboard Paste" popped up with
    "Show desktop notifications" off."""
    import types
    import tuxtalk.config as config
    from tuxtalk import tray
    shown = []
    for wanted in (False, True):
        cfg = types.SimpleNamespace(injection_mode="auto", notify=wanted)
        monkeypatch.setattr(config, "load_config", lambda: cfg)
        monkeypatch.setattr(config, "save_config", lambda c: None)
        monkeypatch.setattr(notify, "notify", lambda title, body: shown.append((wanted, body)))
        t = types.SimpleNamespace(dbus_service=None, _updating_injection_mode=False,
                                  restart_service=lambda _: None)
        tray.DictationTray.set_injection_mode(t, "paste")
    assert shown == [(True, "Input mode: Clipboard Paste")]

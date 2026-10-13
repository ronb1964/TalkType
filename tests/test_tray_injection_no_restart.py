"""Changing Text Injection Mode does not restart the dictation service.

The service rereads injection_mode from config.toml by itself within about a
second, so a restart would only reload the model and leave dictation dead for
several seconds.
"""

import types

from tuxtalk import tray as tray_mod


def test_changing_injection_mode_saves_without_restarting(monkeypatch):
    cfg = types.SimpleNamespace(injection_mode="auto")
    saved = []
    monkeypatch.setattr("tuxtalk.config.load_config", lambda: cfg)
    monkeypatch.setattr("tuxtalk.config.save_config", lambda c: saved.append(c.injection_mode))
    monkeypatch.setattr("tuxtalk.notify.notify", lambda t, b: None)
    restarted = []
    t = types.SimpleNamespace(dbus_service=None, _updating_injection_mode=False,
                              restart_service=lambda _: restarted.append(True))
    tray_mod.DictationTray.set_injection_mode(t, "paste")
    assert saved == ["paste"] and restarted == []

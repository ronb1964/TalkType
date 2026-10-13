"""Hotkey test mode must never be able to leave dictation switched off.

It used to be a blind SIGUSR2 toggle: one signal in from Preferences, one out.
If Preferences crashed with the Test Hotkeys dialog open, the service stayed in
test mode for good; if the service restarted meanwhile, the "off" signal put
the NEW one into test mode. Either way every hotkey was silently ignored.

Now Preferences keeps a flag file fresh while the dialog is open, and the
service ignores one that has gone stale.
"""

import os
import signal
import time

import pytest
from evdev import ecodes

from tuxtalk import app, service_launcher


class FakeEvent:
    type = ecodes.EV_KEY

    def __init__(self, code, value):
        self.code = code
        self.value = value


class FakeConfig:
    beeps = notify = smart_quotes = False
    language = None
    auto_space = auto_period = True
    injection_mode = "type"


HOLD = ecodes.KEY_F8
TOGGLE = ecodes.KEY_F9


@pytest.fixture
def keys(monkeypatch):
    reported, started = [], []
    monkeypatch.setattr(app, "_notify_tray_hotkey_pressed", reported.append)
    monkeypatch.setattr(app, "_grab_keyboards_hiding", lambda *a, **k: None)
    monkeypatch.setattr(app, "start_recording", lambda *a, **k: started.append(True) or True)
    app.state.is_recording = False
    yield reported, started
    app.state.is_recording = False


def press(code):
    app._handle_key_event(FakeEvent(code, 1), "hold", HOLD, TOGGLE,
                          None, set(), [], FakeConfig(), 0)


def flag_path():
    return service_launcher.hotkey_test_flag_path()


def test_a_fresh_flag_reports_presses_instead_of_recording(keys):
    reported, started = keys
    open(flag_path(), "w").close()

    press(HOLD)
    press(TOGGLE)

    assert reported == ["hold", "toggle"]
    assert started == []


def test_without_the_flag_the_hotkeys_record(keys):
    reported, started = keys

    press(HOLD)

    assert reported == []
    assert started == [True]


def test_a_stale_flag_left_by_a_crashed_preferences_is_ignored(keys):
    reported, started = keys
    open(flag_path(), "w").close()
    old = time.time() - service_launcher.HOTKEY_TEST_LEASE_S - 1
    os.utime(flag_path(), (old, old))

    press(HOLD)

    assert reported == []
    assert started == [True], "a dead Preferences left dictation switched off"


def test_preferences_refreshes_well_within_the_lease():
    assert service_launcher.HOTKEY_TEST_REFRESH_S * 2 < service_launcher.HOTKEY_TEST_LEASE_S


def test_signal_handlers_are_installed_before_anything_slow(monkeypatch):
    """SIGUSR1 and SIGUSR2 end a process that doesn't handle them. They were
    installed only after the model loaded, which takes seconds (minutes with a
    download), so a signal in that window killed the service."""
    saved = {s: signal.getsignal(s) for s in (signal.SIGUSR1, signal.SIGUSR2)}

    class Stop(Exception):
        pass

    def first_slow_step():
        assert signal.getsignal(signal.SIGUSR1) == app._handle_sigusr1
        assert signal.getsignal(signal.SIGUSR2) == app._handle_sigusr2
        raise Stop

    from tuxtalk import desktop_identity
    monkeypatch.setattr(desktop_identity, "apply", lambda: None)
    monkeypatch.setattr(app, "_acquire_single_instance", lambda: None)
    monkeypatch.setattr(app, "load_config", first_slow_step)
    try:
        with pytest.raises(Stop):
            app.main()
    finally:
        for s, handler in saved.items():
            signal.signal(s, handler)


def test_a_stray_sigusr2_does_not_toggle_anything(keys):
    reported, started = keys
    app._handle_sigusr2(signal.SIGUSR2, None)

    press(HOLD)

    assert reported == [] and started == [True]

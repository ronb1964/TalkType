"""Recording state reaches the GNOME extension in every mode.

With no tray running, the dictation service owns the bus name itself, and its
app object exposes is_recording as a read-only property. NotifyRecordingState
must not assign it: that raises, RecordingStateChanged is never emitted, and
the extension's icon never turns red.
"""

import types

from tuxtalk.dbus_service import TuxTalkDBusService


def make_service(app):
    s = TuxTalkDBusService.__new__(TuxTalkDBusService)    # no real bus
    s.app = app
    s.signals = []
    s.RecordingStateChanged = lambda on: s.signals.append(on)
    return s


class StandInApp:
    """Like the service's own AppInstance: the state is read from the engine."""

    @property
    def is_recording(self):
        return True


def test_the_stand_in_service_still_emits_the_signal():
    s = make_service(StandInApp())
    s.NotifyRecordingState(True)
    s.NotifyRecordingState(False)
    assert s.signals == [True, False]


def test_the_tray_stores_the_state_and_emits_it():
    app = types.SimpleNamespace(is_recording=False)
    s = make_service(app)
    s.NotifyRecordingState(True)
    assert app.is_recording is True and s.signals == [True]


def test_a_stopped_service_clears_a_stale_recording_state():
    """A service killed mid-recording never sends False itself."""
    app = types.SimpleNamespace(is_recording=True)
    s = make_service(app)
    s.clear_recording_state()
    assert app.is_recording is False and s.signals == [False]
    s.clear_recording_state()                 # already clear: no extra signal
    assert s.signals == [False]


def test_the_tray_clears_recording_when_the_service_stops(monkeypatch):
    from tuxtalk import tray

    app = types.SimpleNamespace(is_recording=True)
    svc = make_service(app)
    svc.claimed_hotkeys = []
    svc.running_engine = None
    svc.HotkeysChanged = lambda keys: None
    svc.ServiceStateChanged = lambda on: None
    t = types.SimpleNamespace(
        _last_service_state=True, dbus_service=svc,
        is_service_running=lambda: False,
        update_icon_status=lambda is_running=None: None,
        update_menu_display=lambda is_running=None: None,
        _release_desktop_hotkeys=lambda: None,
    )
    tray.DictationTray.update_status_and_menu(t, repeat=False)
    assert app.is_recording is False and svc.signals == [False]

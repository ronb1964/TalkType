"""Recording state reaches the GNOME extension in every mode.

With no tray running, the dictation service owns the bus name itself, and its
app object exposes is_recording as a read-only property. NotifyRecordingState
tried to assign it, raised, and never emitted RecordingStateChanged, so the
extension's icon never turned red.
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

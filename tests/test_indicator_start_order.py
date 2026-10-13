"""A quick re-press keeps the indicator in recording mode.

start_recording set is_recording straight away on the recording thread, while
show and hide wait for the GTK loop. A hide still queued from the previous
dictation then ran afterwards and cleared it: no red border, and the orb
pulsed instead of following the voice.
"""
from tuxtalk import recording_indicator as ri


class FakeGLib:
    def __init__(self):
        self.queue = []

    def idle_add(self, fn, *args):
        self.queue.append(lambda: fn(*args))

    def source_remove(self, _id):
        pass

    def run(self):
        while self.queue:
            self.queue.pop(0)()


class _Ind:
    hide_indicator = ri.RecordingIndicator.hide_indicator
    start_recording = ri.RecordingIndicator.start_recording
    stop_recording = ri.RecordingIndicator.stop_recording

    def __init__(self):
        self.is_recording = False
        self.animation_timeout_id = None
        self.style = "orb"

    def hide(self):
        pass


def test_a_pending_hide_does_not_clear_the_next_recording(monkeypatch):
    loop = FakeGLib()
    monkeypatch.setattr(ri, "GLib", loop)
    ind = _Ind()
    ind.hide_indicator()        # end of the previous dictation, not yet run
    ind.start_recording()       # the next one starts before the loop catches up
    loop.run()
    assert ind.is_recording is True

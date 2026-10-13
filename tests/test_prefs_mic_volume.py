"""The Input Volume slider must control the mic TuxTalk records from.

It always changed @DEFAULT_SOURCE@, so with a specific mic picked in the
Microphone dropdown it showed and changed a different device: the test
recording didn't change and another app's mic got turned down.
"""
from types import SimpleNamespace

from tuxtalk import prefs as P
from tuxtalk.prefs import PreferencesWindow

SOURCES = [
    {"name": "alsa_output.pci-0000_14_00.6.analog-stereo.monitor",
     "description": "Monitor of Ryzen HD Audio Controller Analog Stereo",
     "properties": {"device.class": "monitor", "alsa.card": "2"}},
    {"name": "alsa_input.pci-0000_14_00.6.analog-stereo",
     "description": "Ryzen HD Audio Controller Analog Stereo",
     "properties": {"device.class": "sound", "alsa.card": "2"}},
    {"name": "alsa_input.usb-Sennheiser-00.mono-fallback",
     "description": "Sennheiser Profile Mono",
     "properties": {"device.class": "sound", "alsa.card": "3"}},
]


def test_an_alsa_mic_maps_to_its_cards_input_not_the_monitor():
    assert P._pulse_source_for_mic("Sennheiser Profile: USB Audio (hw:3,0)", SOURCES) \
        == "alsa_input.usb-Sennheiser-00.mono-fallback"
    assert P._pulse_source_for_mic("HD-Audio Generic: ALC897 Analog (hw:2,0)", SOURCES) \
        == "alsa_input.pci-0000_14_00.6.analog-stereo"


def test_a_pipewire_device_maps_by_its_description():
    assert P._pulse_source_for_mic("Sennheiser Profile Mono", SOURCES) \
        == "alsa_input.usb-Sennheiser-00.mono-fallback"


def test_an_unknown_mic_maps_to_nothing():
    assert P._pulse_source_for_mic("Some USB Mic (hw:9,0)", SOURCES) is None
    assert P._pulse_source_for_mic("Monitor of Ryzen HD Audio Controller Analog Stereo",
                                   SOURCES) is None


class FakeScale:
    def __init__(self):
        self.sensitive = True
        self.value = None
        self.blocked = False

    def set_sensitive(self, value):
        self.sensitive = value

    def set_value(self, value):
        assert self.blocked, "showing the volume would write it back"
        self.value = value

    def handler_block_by_func(self, fn):
        self.blocked = True

    def handler_unblock_by_func(self, fn):
        self.blocked = False


def _stub(mic):
    reads = []
    d = SimpleNamespace(config={"mic": mic}, volume_scale=FakeScale(),
                        volume_note=SimpleNamespace(visible=None),
                        on_volume_changed=lambda s: None, reads=reads)
    d.volume_note.set_visible = lambda v: setattr(d.volume_note, "visible", v)
    d.get_system_mic_volume = lambda source: reads.append(source) or 42
    return d


def test_the_slider_follows_the_chosen_mic(monkeypatch):
    monkeypatch.setattr(P, "_list_pulse_sources", lambda: SOURCES)
    d = _stub("Sennheiser Profile: USB Audio (hw:3,0)")

    PreferencesWindow._refresh_volume_slider(d)

    assert d._volume_source == "alsa_input.usb-Sennheiser-00.mono-fallback"
    assert d.reads == ["alsa_input.usb-Sennheiser-00.mono-fallback"]
    assert d.volume_scale.sensitive and d.volume_scale.value == 42
    assert d.volume_note.visible is False


def test_system_default_keeps_the_default_source(monkeypatch):
    monkeypatch.setattr(P, "_list_pulse_sources", lambda: SOURCES)
    for mic in ("", "pipewire", "default"):
        d = _stub(mic)
        PreferencesWindow._refresh_volume_slider(d)
        assert d._volume_source == P.DEFAULT_SOURCE


def test_a_mic_with_no_source_disables_the_slider(monkeypatch):
    monkeypatch.setattr(P, "_list_pulse_sources", lambda: SOURCES)
    d = _stub("Some USB Mic (hw:9,0)")

    PreferencesWindow._refresh_volume_slider(d)

    assert d._volume_source is None
    assert not d.volume_scale.sensitive
    assert d.volume_note.visible is True
    assert d.reads == []


def test_a_drag_sets_the_volume_once_on_the_chosen_source(monkeypatch):
    """Each slider tick ran wpctl/pactl on the GTK thread."""
    timers = []
    monkeypatch.setattr(P.GLib, "timeout_add", lambda ms, fn: timers.append(fn) or len(timers))
    calls = []
    d = SimpleNamespace(_volume_source="alsa_input.x",
                        set_system_mic_volume=lambda v, src: calls.append((v, src)))
    d._apply_pending_volume = lambda: PreferencesWindow._apply_pending_volume(d)

    for value in (10, 20, 30, 40):
        PreferencesWindow.on_volume_changed(d, SimpleNamespace(get_value=lambda v=value: v))
    assert len(timers) == 1
    timers[0]()

    assert calls == [(40, "alsa_input.x")]

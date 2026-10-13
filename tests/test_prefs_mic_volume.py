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
     "properties": {"device.class": "monitor", "alsa.card": "2", "alsa.device": "0"}},
    {"name": "alsa_input.pci-0000_14_00.6.analog-stereo",
     "description": "Ryzen HD Audio Controller Analog Stereo",
     "properties": {"device.class": "sound", "alsa.card": "2", "alsa.device": "0"}},
    {"name": "alsa_input.usb-Sennheiser-00.mono-fallback",
     "description": "Sennheiser Profile Mono",
     "properties": {"device.class": "sound", "alsa.card": "3"}},
]
# What the Microphone dropdown lists (sounddevice's input devices).
DEVICES = ["Sennheiser Profile: USB Audio (hw:3,0)",
           "HD-Audio Generic: ALC897 Analog (hw:2,0)",
           "HD-Audio Generic: ALC897 Alt Analog (hw:2,2)",
           "Some USB Mic (hw:9,0)", "Sennheiser Profile Mono", "pipewire", "default"]


def test_an_alsa_mic_maps_to_its_cards_input_not_the_monitor():
    assert P._pulse_source_for_mic("Sennheiser Profile: USB Audio (hw:3,0)", SOURCES) \
        == "alsa_input.usb-Sennheiser-00.mono-fallback"
    assert P._pulse_source_for_mic("HD-Audio Generic: ALC897 Analog (hw:2,0)", SOURCES) \
        == "alsa_input.pci-0000_14_00.6.analog-stereo"


def test_a_pipewire_device_maps_by_its_description():
    assert P._pulse_source_for_mic("Sennheiser Profile Mono", SOURCES) \
        == "alsa_input.usb-Sennheiser-00.mono-fallback"


def test_a_second_input_on_a_card_is_not_mistaken_for_its_first():
    """hw:2,2 matched the card's hw:2,0 source just by the card number."""
    assert P._pulse_source_for_mic("HD-Audio Generic: ALC897 Alt Analog (hw:2,2)",
                                   SOURCES) is None


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
                        _input_device_names=DEVICES,
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


def test_a_mic_that_is_no_longer_listed_uses_the_default_source(monkeypatch):
    """An unplugged mic: the dropdown shows System Default and the service
    records from the default, but the slider was disabled for the old name."""
    monkeypatch.setattr(P, "_list_pulse_sources", lambda: SOURCES)
    d = _stub("Unplugged USB Mic (hw:5,0)")

    PreferencesWindow._refresh_volume_slider(d)

    assert d._volume_source == P.DEFAULT_SOURCE
    assert d.volume_scale.sensitive


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


PACTL_TEXT = """Source #60
\tState: SUSPENDED
\tName: alsa_output.pci-0000_14_00.6.analog-stereo.monitor
\tDescription: Monitor of Ryzen HD Audio Controller Analog Stereo
\tVolume: front-left: 65536 / 100% / 0.00 dB,   front-right: 65536 / 100% / 0.00 dB
\t        balance 0.00
\tProperties:
\t\talsa.card = "2"
\t\tdevice.class = "monitor"
\tFormats:
\t\tpcm
Source #61
\tState: SUSPENDED
\tName: alsa_input.usb-Sennheiser-00.mono-fallback
\tDescription: Sennheiser Profile Mono
\tProperties:
\t\talsa.card = "3"
\t\talsa.device = "0"
\t\tdevice.class = "sound"
\tPorts:
\t\tanalog-input-mic: Microphone (type: Mic, priority: 8700, available)
"""


def test_pactl_without_json_is_read_from_its_text_output(monkeypatch):
    """pactl before 16 (Ubuntu 22.04, Mint 21) has no -f json, so every
    specific mic got no source and the slider was always disabled."""
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw.get("env", {}).get("LC_ALL")))
        if "-f" in cmd:
            return SimpleNamespace(returncode=1, stdout="", stderr="unknown option")
        return SimpleNamespace(returncode=0, stdout=PACTL_TEXT)
    monkeypatch.setattr(P.subprocess, "run", run)

    sources = P._list_pulse_sources()

    assert calls[1] == (["pactl", "list", "sources"], "C")
    assert [s["name"] for s in sources] == [
        "alsa_output.pci-0000_14_00.6.analog-stereo.monitor",
        "alsa_input.usb-Sennheiser-00.mono-fallback"]
    assert sources[1]["description"] == "Sennheiser Profile Mono"
    assert sources[1]["properties"] == {"alsa.card": "3", "alsa.device": "0",
                                        "device.class": "sound"}
    assert P._pulse_source_for_mic("Sennheiser Profile: USB Audio (hw:3,0)", sources) \
        == "alsa_input.usb-Sennheiser-00.mono-fallback"

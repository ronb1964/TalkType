"""Opening Preferences must not change a saved "cuda" to "cpu" by itself.

Without CUDA's files the Device dropdown shows CPU (the service runs on the
processor then). That display change was written into self.config as if the
user had picked it, so the next OK for any unrelated setting saved
device = "cpu" and the user's CUDA choice was gone for good.
"""
try:
    import tomllib
except ImportError:
    import toml as tomllib
from types import SimpleNamespace

from tuxtalk import prefs as P
from tuxtalk.prefs import PreferencesWindow


class FakeCombo:
    def __init__(self):
        self.ids, self.active = [], None

    def remove_all(self):
        self.ids = []

    def append(self, id_, label):
        self.ids.append(id_)

    def set_active_id(self, id_):
        self.active = id_

    def set_tooltip_text(self, text):
        pass


def test_an_unrelated_ok_keeps_the_saved_cuda_choice(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text('device = "cuda"\nbeeps = true\n')
    monkeypatch.setattr(P, "CONFIG_PATH", str(cfg))
    from tuxtalk import whisper_vulkan
    monkeypatch.setattr(whisper_vulkan, "is_offered", lambda: False)

    opened = {"device": "cuda", "beeps": True, "model": "small", "language_mode": "auto"}
    d = SimpleNamespace(config=dict(opened), _config_at_open=dict(opened),
                        device_combo=FakeCombo(), _handle_autostart=lambda v: None,
                        _check_cuda_availability=lambda: False, _has_nvidia=lambda: False)

    PreferencesWindow._refresh_device_options(d)
    assert d.device_combo.active == "cpu"          # what the service really uses

    d.config["beeps"] = False                       # the user's only change
    assert PreferencesWindow.save_config(d) is True

    saved = tomllib.loads(cfg.read_text())
    assert saved["device"] == "cuda"
    assert saved["beeps"] is False

"""After the CUDA download: switch for real, and never slow Parakeet down.

The download used to save device = "cuda" by itself, which also moved the
baseline Preferences diffs against, so OK found no change and never restarted
the service (Ron, 0.14.5 test: config said cuda, dictation stayed on Vulkan).
And Parakeet can't use CUDA, so switching it there would move it from the
graphics card to the processor. Now Parakeet users are asked whether to move
to Whisper Small on CUDA, and any switch goes through Apply.
"""
from types import SimpleNamespace

import pytest


@pytest.fixture
def prefs():
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "3.0")
    from talktype import prefs
    return prefs


class _Box:
    def __init__(self, answer, asked):
        self.answer, self.asked = answer, asked

    def format_secondary_text(self, text):
        self.asked.append(text)

    def add_button(self, *a):
        return SimpleNamespace(get_style_context=lambda: SimpleNamespace(add_class=lambda c: None))

    def set_default_response(self, r):
        pass

    def run(self):
        return self.answer

    def destroy(self):
        pass


def _stub(prefs, model, answer, monkeypatch):
    asked = []
    monkeypatch.setattr(prefs, "message_dialog", lambda **k: _Box(answer, asked))
    stub = SimpleNamespace(config={"model": model, "device": "vulkan"}, window=None,
                           applied=[], asked=asked)
    stub.on_apply = lambda button: stub.applied.append(dict(stub.config))
    stub._set_choice = lambda key, value: stub.config.__setitem__(key, value)
    return stub


def test_a_whisper_model_switches_to_cuda_through_apply(prefs, monkeypatch):
    stub = _stub(prefs, "small", None, monkeypatch)
    prefs.PreferencesWindow._after_cuda_download(stub)
    assert stub.asked == []
    assert stub.applied == [{"model": "small", "device": "cuda"}]


def test_parakeet_is_asked_and_can_move_to_whisper_small(prefs, monkeypatch):
    stub = _stub(prefs, "parakeet-v3", prefs.Gtk.ResponseType.YES, monkeypatch)
    prefs.PreferencesWindow._after_cuda_download(stub)
    assert len(stub.asked) == 1
    assert stub.applied == [{"model": "small", "device": "cuda"}]


def test_parakeet_can_stay_put(prefs, monkeypatch):
    stub = _stub(prefs, "parakeet-v3", prefs.Gtk.ResponseType.NO, monkeypatch)
    prefs.PreferencesWindow._after_cuda_download(stub)
    assert stub.applied == []
    assert stub.config == {"model": "parakeet-v3", "device": "vulkan"}


def test_the_download_no_longer_writes_the_config_itself():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "src/talktype/cuda_helper.py").read_text()
    assert "Automatically enable GPU mode" not in src

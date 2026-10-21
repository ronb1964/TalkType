"""Parakeet engine wiring.

Parakeet is offered as one more model name ("parakeet-v3") so that every model
picker, the config validator and the download dialogs handle it without their
own special cases. These tests pin down the places where it genuinely differs
from Whisper: how "is it downloaded?" is answered and how dictation audio
reaches it. Where its files come from is tests/test_parakeet_ultra.py.
"""
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def test_parakeet_is_offered_valid_and_downloadable():
    from tuxtalk.config import VALID_MODELS
    from tuxtalk.model_helper import MODEL_DISPLAY_SIZES, OFFERED_MODELS
    from tuxtalk.parakeet_engine import PARAKEET_MODEL

    assert PARAKEET_MODEL in OFFERED_MODELS
    assert PARAKEET_MODEL in VALID_MODELS
    assert PARAKEET_MODEL in MODEL_DISPLAY_SIZES


def test_every_offered_model_has_a_label_on_every_picker():
    """The picker indexes a label dict by model id; a missing key crashes the
    screen as it opens. (First run's card has no full picker.)"""
    from tuxtalk.model_helper import OFFERED_MODELS

    for path, dict_name in (("src/tuxtalk/prefs.py", "_MODEL_DISPLAY"),):
        source = (ROOT / path).read_text()
        body = re.search(dict_name + r" = \{(.*?)\n\s*\}", source, re.S).group(1)
        keys = set(re.findall(r'"([^"]+)":', body))
        missing = set(OFFERED_MODELS) - keys
        assert not missing, f"{path} {dict_name} has no label for {sorted(missing)}"


def test_whisper_downloads_are_not_filtered(monkeypatch):
    import huggingface_hub
    from tuxtalk import model_helper

    monkeypatch.setattr(
        huggingface_hub, "list_repo_tree",
        lambda repo_id, recursive=True: [SimpleNamespace(path="model.bin", size=10),
                                         SimpleNamespace(path="README.md", size=1)],
    )
    files = model_helper._files_to_download("Systran/faster-whisper-small")
    assert {p for p, _ in files} == {"model.bin", "README.md"}


def test_cache_checks_use_parakeet_files(monkeypatch):
    from tuxtalk import model_helper

    monkeypatch.setattr(model_helper, "_parakeet_cached_dir", lambda: None)
    assert model_helper.is_model_cached_fast("parakeet-v3") is False

    monkeypatch.setattr(model_helper, "_parakeet_cached_dir", lambda: "/some/dir")
    assert model_helper.is_model_cached_fast("parakeet-v3") is True


def test_dictation_audio_goes_to_parakeet(monkeypatch):
    from tuxtalk import app
    from tuxtalk.parakeet_engine import ParakeetModel

    received = []
    fake = ParakeetModel.__new__(ParakeetModel)  # skip loading the real model
    fake.recognize = lambda audio: received.append(audio) or "Hello there."
    monkeypatch.setattr(app, "model", fake, raising=False)

    audio = np.zeros(16000, dtype=np.float32)
    assert app._transcribe_audio(audio, language="de") == "Hello there."
    assert received and received[0] is audio


def test_parakeet_silence_returns_none(monkeypatch):
    from tuxtalk import app
    from tuxtalk.parakeet_engine import ParakeetModel

    fake = ParakeetModel.__new__(ParakeetModel)
    fake.recognize = lambda audio: ""
    monkeypatch.setattr(app, "model", fake, raising=False)

    assert app._transcribe_audio(np.zeros(8000, dtype=np.float32), language=None) is None


def test_the_download_question_names_the_model_as_the_menus_do(monkeypatch):
    """It said "Download Small Model?" where the menus said "Whisper Small"
    (review of 0.17)."""
    from tuxtalk import model_helper
    asked = []

    class Question:
        def __init__(self, **kwargs):
            asked.append(kwargs["text"])
        def format_secondary_text(self, text): pass
        def set_position(self, position): pass
        def destroy(self): pass
        def run(self):
            return model_helper.Gtk.ResponseType.CANCEL

    monkeypatch.setattr(model_helper, "is_model_cached_fast", lambda m: False)
    monkeypatch.setattr(model_helper, "message_dialog", lambda **k: Question(**k))
    assert model_helper.download_model_with_progress("small") is None
    assert asked == ["Download Whisper Small Model?"]


def test_menus_show_the_device_parakeet_really_uses():
    """Picking Parakeet in Preferences can leave device = "cuda" in the config;
    both the tray and the GNOME extension (via GetDeviceType) must say CPU."""
    from tuxtalk.parakeet_engine import effective_device
    assert effective_device("parakeet-v3", "cuda") == "cpu"
    assert effective_device("large-v3", "cuda") == "cuda"
    assert effective_device("small", "cpu") == "cpu"


def test_parakeet_is_on_the_graphics_chip_only_once_its_vulkan_files_are_there(monkeypatch):
    from tuxtalk import whisper_vulkan as wv
    from tuxtalk.parakeet_engine import effective_device
    monkeypatch.setattr(wv, "is_installed", lambda m: False)
    assert effective_device("parakeet-v3", "vulkan") == "cpu"
    monkeypatch.setattr(wv, "is_installed", lambda m: True)
    assert effective_device("parakeet-v3", "vulkan") == "vulkan"
    assert effective_device("parakeet-v3", "cuda") == "cpu"     # CUDA has no Parakeet

    from tuxtalk.dbus_service import TuxTalkDBusService
    svc = TuxTalkDBusService.__new__(TuxTalkDBusService)
    svc.app = SimpleNamespace(config=SimpleNamespace(model="parakeet-v3", device="cuda"))
    assert TuxTalkDBusService.GetDeviceType(svc) == "cpu"


def _parakeet_saying(monkeypatch, text, nobody_talked):
    from tuxtalk import app, silence
    from tuxtalk.parakeet_engine import ParakeetModel
    fake = ParakeetModel.__new__(ParakeetModel)
    fake.recognize = lambda audio: text
    monkeypatch.setattr(app, "model", fake, raising=False)
    monkeypatch.setattr(silence, "has_no_speech", lambda a, sr: nobody_talked)
    return app._transcribe_audio(np.zeros(16000, dtype=np.float32), language=None)


def test_parakeet_inventing_mm_hmm_in_silence_types_nothing(monkeypatch):
    """0.15.0 testing: an F9 tap with nothing said typed "Mm-hmm." into Konsole."""
    assert _parakeet_saying(monkeypatch, "Mm-hmm.", nobody_talked=True) is None


def test_parakeet_keeps_a_real_mm_hmm(monkeypatch):
    assert _parakeet_saying(monkeypatch, "Mm-hmm.", nobody_talked=False) == "Mm-hmm."


def test_parakeet_keeps_real_words_even_in_a_quiet_recording(monkeypatch):
    """Only stock fillers are judged, never a real sentence."""
    assert _parakeet_saying(monkeypatch, "Hello there.", nobody_talked=True) == "Hello there."


def test_nothing_recognized_plays_the_cancel_beep(monkeypatch):
    """A recording that types nothing ends with the cancel beep, not silence."""
    from tuxtalk import app, silence
    beeps = []
    monkeypatch.setattr(app, "_beep", lambda on, *tone: beeps.append(tone))
    monkeypatch.setattr(silence, "is_speechless_tap", lambda a, sr: False)
    monkeypatch.setattr(app, "_transcribe_audio", lambda *a: None)
    app._transcribe_and_inject([np.ones(16000, dtype=np.int16).tobytes()], 16000, True, False, False)
    assert beeps == [app.CANCEL_BEEP]

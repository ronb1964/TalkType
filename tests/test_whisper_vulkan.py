"""Whisper on AMD / Intel graphics through whisper.cpp's Vulkan engine.

The parts that need a real graphics chip (the engine itself) were checked by
hand on an RTX 4070 Super and a Ryzen 7800X3D's built-in Radeon; these cover
everything around them.
"""
import io
import wave

import numpy as np
import pytest

from talktype import whisper_vulkan as wv

# Exactly what the engine printed on the development machine (NVIDIA card plus
# the Ryzen's built-in AMD graphics).
REAL_DEVICE_LIST = """\
ggml_vulkan: Found 2 Vulkan devices:
ggml_vulkan: 0 = NVIDIA GeForce RTX 4070 SUPER (NVIDIA) | uma: 0 | fp16: 1 | bf16: 1 | fp4: 0 | warp size: 32 | shared memory: 49152 | int dot: 1 | matrix cores: NV_coopmat2
ggml_vulkan: 1 = AMD Ryzen 7 7800X3D 8-Core Processor (RADV RAPHAEL_MENDOCINO) (radv) | uma: 1 | fp16: dot2 | bf16: 0 | fp4: 0 | warp size: 32 | shared memory: 65536 | int dot: 1 | matrix cores: none
load_backend: loaded Vulkan backend from /x/libggml-vulkan.so
"""


def test_parses_the_device_list_the_engine_prints():
    assert wv.parse_vulkan_devices(REAL_DEVICE_LIST) == [
        (0, "NVIDIA GeForce RTX 4070 SUPER (NVIDIA)", True, False),
        (1, "AMD Ryzen 7 7800X3D 8-Core Processor (RADV RAPHAEL_MENDOCINO) (radv)", False, True),
    ]


def test_picks_the_amd_chip_over_nvidia():
    assert wv.choose_device(wv.parse_vulkan_devices(REAL_DEVICE_LIST)) == 1


def test_prefers_a_graphics_card_over_built_in_graphics():
    devices = [(0, "AMD Radeon 780M (radv)", False, True),
               (1, "Intel Arc A770 (Intel open-source Mesa driver)", False, False)]
    assert wv.choose_device(devices) == 1


def test_no_amd_or_intel_chip_means_no_device():
    assert wv.choose_device([(0, "NVIDIA GeForce RTX 3060", True, False)]) is None
    assert wv.choose_device([]) is None


def test_finds_amd_and_intel_chips_from_the_kernel(tmp_path):
    for card, vendor in (("card0", "0x10de"), ("card1", "0x1002"), ("card1-DP-1", None)):
        (tmp_path / card / "device").mkdir(parents=True)
        if vendor:
            (tmp_path / card / "device" / "vendor").write_text(vendor + "\n")
    assert wv.graphics_vendors(str(tmp_path)) == {"0x10de", "0x1002"}


def test_offered_only_with_amd_or_intel_graphics_and_vulkan(monkeypatch):
    monkeypatch.setattr(wv, "vulkan_available", lambda: True)
    monkeypatch.setattr(wv, "graphics_vendors", lambda: {wv.NVIDIA_VENDOR})
    assert wv.is_offered() is False
    monkeypatch.setattr(wv, "graphics_vendors", lambda: {wv.NVIDIA_VENDOR, wv.INTEL_VENDOR})
    assert wv.is_offered() is True
    monkeypatch.setattr(wv, "vulkan_available", lambda: False)
    assert wv.is_offered() is False


def test_every_whisper_model_has_a_whisper_cpp_file_and_parakeet_does_not():
    from talktype.model_helper import OFFERED_MODELS
    from talktype.parakeet_engine import is_parakeet
    for model in OFFERED_MODELS:
        assert wv.supports_model(model) != is_parakeet(model)


def test_wav_is_16_bit_mono_and_keeps_the_samples():
    audio = np.array([0.0, 0.5, -0.5, 1.5], dtype=np.float32)   # 1.5 must clip
    with wave.open(io.BytesIO(wv.wav_bytes(audio))) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000)
        samples = np.frombuffer(w.readframes(4), dtype="<i2")
    assert list(samples) == [0, 16383, -16383, 32767]


def test_multipart_carries_fields_and_the_file():
    body, content_type = wv.multipart({"language": "en"}, b"RIFFdata")
    boundary = content_type.split("boundary=")[1]
    assert body.startswith(f"--{boundary}\r\n".encode())
    assert b'name="language"\r\n\r\nen\r\n' in body
    assert b'filename="audio.wav"' in body and b"RIFFdata" in body
    assert body.endswith(f"--{boundary}--\r\n".encode())


def test_reads_text_and_no_speech_from_the_reply():
    reply = {"text": " Hello there. Bye.", "segments": [
        {"text": " Hello there.", "no_speech_prob": 0.02},
        {"text": " Bye.", "no_speech_prob": 0.4}]}
    assert wv.parse_result(reply) == ("Hello there. Bye.", 0.4)
    assert wv.parse_result({"text": " Just text "}) == ("Just text", 0.0)


@pytest.mark.parametrize("gpu, cpu, worth_it", [
    (0.38, 6.2, True),      # RTX 4070 Super vs Ryzen 7800X3D, large model
    (6.27, 6.18, False),    # the Ryzen's tiny built-in graphics: a tie at best
    (0.9, 1.0, False),      # 10% isn't worth an extra engine
    (0.8, 1.0, True),
])
def test_graphics_is_used_only_when_clearly_faster(gpu, cpu, worth_it):
    assert wv.graphics_is_worth_it(gpu, cpu) is worth_it


def test_speed_check_reads_whisper_cli_timings(monkeypatch):
    runs = []

    class Done:
        returncode = 0

        def __init__(self, seconds):
            self.stderr = f"whisper_print_timings:    total time =  {seconds * 1000:.2f} ms\n"

    def fake_run(cmd, **kw):
        runs.append(cmd)
        return Done(6.2 if "-ng" in cmd else 0.4)

    monkeypatch.setattr(wv.subprocess, "run", fake_run)
    monkeypatch.setattr(wv, "model_path", lambda m: "/models/x.bin")
    assert wv.speed_check("large-v3", 1, threads=8) == (0.4, 6.2)
    assert [("-dev" in r, "-ng" in r) for r in runs] == [(True, False), (True, False), (False, True)]


@pytest.mark.parametrize("text, cleaned", [
    (" [BLANK_AUDIO]", ""),                                   # silence, measured
    (" [MUSIC] Okay let's go [NOISE]", "Okay let's go"),
    (" I wrote [sic] in the note", "I wrote [sic] in the note"),   # real brackets stay
])
def test_non_speech_markers_are_never_typed(text, cleaned):
    reply = {"text": text, "segments": [{"text": text, "no_speech_prob": 0.0}]}
    assert wv.parse_result(reply)[0] == cleaned


# --- the dictation service ----------------------------------------------------

class FakeEngine(wv.VulkanWhisperModel):
    def __init__(self, model_name, device_index):
        self.model_name, self.device_index = model_name, device_index

    def transcribe(self, audio, language=None):
        return "Thank you.", 0.95          # a high, untrustworthy no-speech score


def _settings(**kw):
    from talktype.config import Settings
    return Settings(**{"model": "small", "device": "vulkan", **kw})


def test_service_runs_whisper_on_the_amd_or_intel_chip(monkeypatch):
    from talktype import app
    monkeypatch.setattr(wv, "is_installed", lambda m: True)
    monkeypatch.setattr(wv, "find_device", lambda: 1)
    monkeypatch.setattr(wv, "VulkanWhisperModel", FakeEngine)
    model = app.build_model(_settings())
    assert isinstance(model, FakeEngine) and (model.model_name, model.device_index) == ("small", 1)


def test_service_falls_back_to_the_processor_when_the_engine_is_missing(monkeypatch):
    from talktype import app
    loaded, told = [], []
    monkeypatch.setattr(wv, "is_installed", lambda m: False)
    monkeypatch.setattr(app, "_notify", lambda *a: told.append(a))
    monkeypatch.setattr("talktype.model_helper.download_model_with_progress",
                        lambda model, device, compute_type, **k: loaded.append(device) or "cpu-model")
    settings = _settings()
    assert app.build_model(settings) == "cpu-model"
    assert loaded == ["cpu"] and told
    assert settings.device == "vulkan"        # the user's choice is not overwritten


def test_parakeet_never_uses_the_graphics_engine(monkeypatch):
    from talktype import app
    from talktype.parakeet_engine import PARAKEET_MODEL
    monkeypatch.setattr(wv, "VulkanWhisperModel", lambda *a: pytest.fail("used the graphics engine"))
    monkeypatch.setattr("talktype.model_helper.download_model_with_progress",
                        lambda model, device, compute_type, **k: "parakeet-model")
    assert app.build_model(_settings(model=PARAKEET_MODEL)) == "parakeet-model"


def test_transcription_ignores_the_engines_no_speech_score(monkeypatch):
    """A real "Thank you." must survive even though the engine scored it 0.95."""
    from talktype import app
    monkeypatch.setattr(app, "model", FakeEngine("small", 1), raising=False)
    assert app._transcribe_audio(np.zeros(16000, dtype=np.float32), "en") == "Thank you."

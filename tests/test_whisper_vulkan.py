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


def test_picks_the_graphics_card_over_built_in_graphics_any_brand():
    """On the development machine: the RTX 4070 Super, not the Ryzen's tiny
    built-in Radeon (16x faster than the CPU vs no faster at all)."""
    assert wv.choose_device(wv.parse_vulkan_devices(REAL_DEVICE_LIST)) == 0


def test_prefers_a_graphics_card_over_built_in_graphics():
    devices = [(0, "AMD Radeon 780M (radv)", False, True),
               (1, "Intel Arc A770 (Intel open-source Mesa driver)", False, False)]
    assert wv.choose_device(devices) == 1


def test_an_nvidia_card_alone_is_used_and_no_chip_means_none():
    assert wv.choose_device([(0, "NVIDIA GeForce RTX 3060", True, False)]) == 0
    assert wv.choose_device([(0, "AMD Radeon 780M (radv)", False, True)]) == 0
    assert wv.choose_device([]) is None


def test_finds_amd_and_intel_chips_from_the_kernel(tmp_path):
    for card, vendor in (("card0", "0x10de"), ("card1", "0x1002"), ("card1-DP-1", None)):
        (tmp_path / card / "device").mkdir(parents=True)
        if vendor:
            (tmp_path / card / "device" / "vendor").write_text(vendor + "\n")
    assert wv.graphics_vendors(str(tmp_path)) == {"0x10de", "0x1002"}


def test_offered_with_any_graphics_chip_and_vulkan(monkeypatch):
    monkeypatch.setattr(wv, "vulkan_available", lambda: True)
    for vendors in ({wv.NVIDIA_VENDOR}, {wv.AMD_VENDOR}, {wv.INTEL_VENDOR}):
        monkeypatch.setattr(wv, "graphics_vendors", lambda v=vendors: v)
        assert wv.is_offered() is True
    monkeypatch.setattr(wv, "graphics_vendors", lambda: set())       # e.g. a VM
    assert wv.is_offered() is False
    monkeypatch.setattr(wv, "graphics_vendors", lambda: {wv.NVIDIA_VENDOR})
    monkeypatch.setattr(wv, "vulkan_available", lambda: False)
    assert wv.is_offered() is False


def test_every_offered_model_has_a_file_in_whisper_cpp_format():
    """Parakeet included: whisper.cpp 1.9.4 runs it too (libparakeet)."""
    from talktype.model_helper import OFFERED_MODELS
    for model in OFFERED_MODELS:
        assert wv.supports_model(model), model


def test_parakeet_comes_from_its_own_repo_and_whisper_from_whisper_cpps():
    from talktype.parakeet_engine import PARAKEET_MODEL
    assert wv.model_repo(PARAKEET_MODEL) == "ggml-org/parakeet-GGUF"
    assert wv.MODEL_FILES[PARAKEET_MODEL][0] == "ggml-parakeet-tdt-0.6b-v3-q8_0.bin"
    assert wv.model_repo("small") == "ggerganov/whisper.cpp"


def _engine(tmp_path, monkeypatch, *names):
    """An engine folder holding executables *names*."""
    monkeypatch.setattr(wv, "_engine_dir", lambda: str(tmp_path))
    for name in names:
        f = tmp_path / name
        f.write_text("")
        f.chmod(0o755)


def test_parakeet_needs_an_engine_built_with_parakeet(tmp_path, monkeypatch):
    """Engine build 1 (TalkType 0.12.0 to 0.13.1) has no Parakeet in it. It
    still counts as installed for Whisper, so nobody re-downloads it."""
    from talktype.parakeet_engine import PARAKEET_MODEL
    _engine(tmp_path, monkeypatch, "whisper-server")
    assert wv.is_engine_installed() and wv.is_engine_installed("small")
    assert not wv.is_engine_installed(PARAKEET_MODEL)
    _engine(tmp_path, monkeypatch, "whisper-server", "parakeet-cli", "libparakeet.so")
    assert wv.is_engine_installed(PARAKEET_MODEL)


def test_engine_download_fetches_again_when_parakeet_is_missing(tmp_path, monkeypatch):
    from talktype.parakeet_engine import PARAKEET_MODEL
    _engine(tmp_path, monkeypatch, "whisper-server")
    fetched = []
    monkeypatch.setattr("talktype.download_utils.download_file",
                        lambda url, *a, **k: fetched.append(url) or False)
    assert wv.make_engine_download_func("small")(lambda *a: None, None) is True
    assert fetched == []
    wv.make_engine_download_func(PARAKEET_MODEL)(lambda *a: None, None)
    assert fetched == [wv.ENGINE_URL]


def test_engine_build_2_has_its_own_asset_so_build_1_stays_valid():
    """0.12.0 to 0.13.1 check build 1's SHA256, so build 2 can't reuse its name."""
    assert wv.ENGINE_ASSET == "talktype-whisper-vulkan-1.9.4-b2-x64.tar.gz"
    assert wv.ENGINE_TAG == "whisper-vulkan-1.9.4-b2"
    assert wv.ENGINE_NAME == "talktype-whisper-vulkan-1.9.4"    # unpacks over build 1


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


def test_parakeet_speed_check_uses_parakeet_cli_without_its_load_time(monkeypatch):
    """Loading onto a graphics card takes longer than onto the processor, and
    Parakeet transcribes the sample so fast that counting the load would hide
    most of the difference."""
    from talktype.parakeet_engine import PARAKEET_MODEL
    runs = []

    class Done:
        returncode = 0

        def __init__(self, load, total):
            self.stderr = (f"parakeet_print_timings:     load time =   {load * 1000:.2f} ms\n"
                           f"parakeet_print_timings:    total time =   {total * 1000:.2f} ms\n")

    def fake_run(cmd, **kw):
        runs.append(cmd)
        return Done(0.08, 0.84) if "-ng" in cmd else Done(0.20, 0.26)

    monkeypatch.setattr(wv.subprocess, "run", fake_run)
    monkeypatch.setattr(wv, "model_path", lambda m: "/models/p.bin")
    gpu, cpu = wv.speed_check(PARAKEET_MODEL, 0, threads=4)
    assert (round(gpu, 2), round(cpu, 2)) == (0.06, 0.76)
    assert all(r[0].endswith("parakeet-cli") for r in runs)


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


def test_parakeet_never_uses_the_whisper_engine(monkeypatch):
    from talktype import app
    from talktype.parakeet_engine import PARAKEET_MODEL
    monkeypatch.setattr(wv, "VulkanWhisperModel", lambda *a: pytest.fail("used the Whisper engine"))
    monkeypatch.setattr(wv, "is_installed", lambda m: False)
    monkeypatch.setattr("talktype.model_helper.download_model_with_progress",
                        lambda model, device, compute_type, **k: "parakeet-model")
    assert app.build_model(_settings(model=PARAKEET_MODEL)) == "parakeet-model"


class FakeParakeetGpu:
    def __init__(self, device_index):
        self.device_index = device_index

    def recognize(self, audio):
        return "Hello there."


def test_service_runs_parakeet_on_the_graphics_chip(monkeypatch):
    from talktype import app, parakeet_gpu
    from talktype.parakeet_engine import PARAKEET_MODEL
    monkeypatch.setattr(wv, "is_installed", lambda m: True)
    monkeypatch.setattr(wv, "find_device", lambda: 0)
    monkeypatch.setattr(parakeet_gpu, "ParakeetGpuModel", FakeParakeetGpu)
    model = app.build_model(_settings(model=PARAKEET_MODEL))
    assert isinstance(model, FakeParakeetGpu) and model.device_index == 0


def test_parakeet_on_vulkan_without_its_files_quietly_uses_the_processor(monkeypatch):
    """Someone on 0.13.1 with Vulkan as the device and Parakeet as the model
    has never downloaded Parakeet's graphics files. They keep the processor,
    as before, without a warning at every start."""
    from talktype import app, parakeet_gpu
    from talktype.parakeet_engine import PARAKEET_MODEL
    told = []
    monkeypatch.setattr(wv, "is_installed", lambda m: False)
    monkeypatch.setattr(parakeet_gpu, "ParakeetGpuModel", lambda *a: pytest.fail("started the helper"))
    monkeypatch.setattr(app, "_notify", lambda *a: told.append(a))
    monkeypatch.setattr("talktype.model_helper.download_model_with_progress",
                        lambda model, device, compute_type, **k: f"parakeet-on-{device}")
    assert app.build_model(_settings(model=PARAKEET_MODEL)) == "parakeet-on-cpu"
    assert told == []


def test_parakeet_falls_back_to_the_processor_when_the_helper_fails(monkeypatch):
    from talktype import app, parakeet_gpu
    from talktype.parakeet_engine import PARAKEET_MODEL
    told = []

    def broken(device_index):
        raise RuntimeError("driver said no")

    monkeypatch.setattr(wv, "is_installed", lambda m: True)
    monkeypatch.setattr(wv, "find_device", lambda: 0)
    monkeypatch.setattr(parakeet_gpu, "ParakeetGpuModel", broken)
    monkeypatch.setattr(app, "_notify", lambda *a: told.append(a))
    monkeypatch.setattr("talktype.model_helper.download_model_with_progress",
                        lambda model, device, compute_type, **k: f"parakeet-on-{device}")
    settings = _settings(model=PARAKEET_MODEL)
    assert app.build_model(settings) == "parakeet-on-cpu"
    assert told and settings.device == "vulkan"


def test_parakeet_on_the_graphics_chip_transcribes(monkeypatch):
    from talktype import app, parakeet_gpu
    gpu = parakeet_gpu.ParakeetGpuModel.__new__(parakeet_gpu.ParakeetGpuModel)
    monkeypatch.setattr(parakeet_gpu.ParakeetGpuModel, "recognize", lambda self, a: "Hello there.")
    monkeypatch.setattr(app, "model", gpu, raising=False)
    assert app._transcribe_audio(np.zeros(16000, dtype=np.float32), None) == "Hello there."


def test_transcription_ignores_the_engines_no_speech_score(monkeypatch):
    """A real "Thank you." must survive even though the engine scored it 0.95."""
    from talktype import app
    monkeypatch.setattr(app, "model", FakeEngine("small", 1), raising=False)
    assert app._transcribe_audio(np.zeros(16000, dtype=np.float32), "en") == "Thank you."


# --- first-run setup: the light choice for NVIDIA ---------------------------------

def test_first_run_light_choice_switches_the_device_once_the_engine_is_there(monkeypatch):
    from talktype import welcome_dialog as wd
    from talktype.config import Settings
    saved = []
    monkeypatch.setattr(wv, "is_engine_installed", lambda *a: True)
    monkeypatch.setattr("talktype.config.load_config", lambda: Settings())
    monkeypatch.setattr("talktype.config.save_config", lambda c: saved.append(c.device))
    wd._setup_vulkan_engine_first_run()
    assert saved == ["vulkan"]


def test_first_run_light_choice_stays_on_the_processor_if_the_engine_never_arrives(monkeypatch):
    from talktype import welcome_dialog as wd
    import talktype.download_progress_dialog as dpd
    saved = []

    class NoDownload:
        def __init__(self, **kw): pass
        def add_task(self, task): pass
        def run(self): return {}

    monkeypatch.setattr(wv, "is_engine_installed", lambda *a: False)
    monkeypatch.setattr(dpd, "UnifiedDownloadDialog", NoDownload)
    monkeypatch.setattr("talktype.config.save_config", lambda c: saved.append(c.device))
    wd._setup_vulkan_engine_first_run()
    assert saved == []


def test_first_run_model_download_is_skipped_when_already_there(monkeypatch):
    from talktype import welcome_dialog as wd
    monkeypatch.setattr(wv, "is_engine_installed", lambda *a: True)
    monkeypatch.setattr(wv, "model_path", lambda m: "/models/x.bin")
    assert wd._download_vulkan_model_first_run("small") is True


def test_first_run_parakeet_on_vulkan_fetches_an_engine_that_can_run_it(monkeypatch):
    """Engine build 1 can't run Parakeet, so it's fetched again with the model."""
    from talktype import welcome_dialog as wd
    import talktype.download_progress_dialog as dpd
    added = []

    class Dialog:
        def __init__(self, **kw): pass
        def add_task(self, task): added.append(task.name)
        def run(self): return {}

    monkeypatch.setattr(wv, "is_engine_installed", lambda *a: not a or a[0] != "parakeet-v3")
    monkeypatch.setattr(wv, "model_path", lambda m: None)
    monkeypatch.setattr(dpd, "UnifiedDownloadDialog", Dialog)
    assert wd._download_vulkan_model_first_run("parakeet-v3") is False
    assert added == ["Graphics engine", "Speech model"]


def test_first_run_vulkan_uses_the_preferences_speed_check(monkeypatch):
    """First run switched to Vulkan without timing it, so weak built-in
    graphics could end up slower than the processor."""
    from talktype import welcome_dialog as wd
    seen = []
    monkeypatch.setattr("talktype.vulkan_setup_dialogs.run_speed_check",
                        lambda parent, model: seen.append(model) or False)
    assert wd._vulkan_speed_check_first_run("parakeet-v3") is False
    assert seen == ["parakeet-v3"]


def test_first_run_speed_check_error_keeps_the_processor(monkeypatch):
    from talktype import welcome_dialog as wd

    def boom(parent, model):
        raise RuntimeError("no Vulkan device")

    monkeypatch.setattr("talktype.vulkan_setup_dialogs.run_speed_check", boom)
    assert wd._vulkan_speed_check_first_run("small") is False


def test_first_run_only_uses_vulkan_when_it_wins_the_speed_check():
    """The download alone no longer settles it."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "src" / "talktype" / "welcome_dialog.py").read_text()
    assert ("vulkan_ready = (_download_vulkan_model_first_run(selected_model)\n"
            "                                    and _vulkan_speed_check_first_run(selected_model))") in src

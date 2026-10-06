"""The tray and GNOME menu say what really runs, not just what's configured.

After a fallback they used to show the settings, so the Device line could say
"GPU (Vulkan)" while the processor did the work. The dictation service now
reports the model and device it actually loaded (NotifyRunningEngine).
"""
import types

import pytest

from talktype.dbus_service import TalkTypeDBusService
from talktype.tray import engine_status, preset_notice


@pytest.mark.parametrize("cfg_model,cfg_device,running,expected", [
    ("parakeet-v3", "vulkan", ("parakeet-v3", "vulkan"), ("parakeet-v3", "GPU (Vulkan)")),
    ("parakeet-v3", "vulkan", ("parakeet-v3", "cpu"), ("parakeet-v3", "CPU (Vulkan didn't start)")),
    ("large-v3", "cuda", ("large-v3", "cpu"), ("large-v3", "CPU (CUDA didn't start)")),
    ("parakeet-v3", "cuda", None, ("parakeet-v3", "CPU (Parakeet can't use CUDA)")),
    ("parakeet-v3", "cuda", ("parakeet-v3", "cpu"), ("parakeet-v3", "CPU (Parakeet can't use CUDA)")),
    ("small", "cpu", None, ("small", "CPU")),
    ("large-v3", "vulkan", None, ("large-v3", "GPU (Vulkan)")),   # not reported yet: the setting
    ("medium", "cuda", ("small", "cuda"), ("small", "GPU (CUDA)")),  # model fallback shows
])
def test_status_lines(cfg_model, cfg_device, running, expected):
    assert engine_status(cfg_model, cfg_device, running) == expected


def test_parakeet_preset_on_a_gpu_machine_says_how_to_use_it():
    text = preset_notice("Fast & Accurate", "parakeet-v3", "cpu", gpu_offered=True)
    assert "on the processor" in text and "Vulkan" in text


def test_no_gpu_hint_without_a_usable_graphics_chip():
    assert "Vulkan" not in preset_notice("Balanced", "small", "cpu", gpu_offered=False)


def test_gpu_preset_says_which_engine():
    assert "graphics card (CUDA)" in preset_notice("Most Accurate", "large-v3", "cuda", True)


@pytest.fixture
def svc(monkeypatch):
    # Parakeet's Vulkan files "downloaded", so the setting alone says vulkan.
    monkeypatch.setattr("talktype.whisper_vulkan.is_installed", lambda m: True)
    s = TalkTypeDBusService.__new__(TalkTypeDBusService)    # no real bus
    s.app = types.SimpleNamespace(config=types.SimpleNamespace(model="parakeet-v3", device="vulkan"))
    s.running_engine = None
    s.claimed_hotkeys = []
    s.changed = []
    s.ModelChanged = lambda m: s.changed.append(m)
    return s


def test_the_service_report_wins_over_the_settings(svc):
    assert svc.GetDeviceType() == "vulkan"
    svc.NotifyRunningEngine("parakeet-v3", "cpu")
    assert svc.GetDeviceType() == "cpu" and svc.GetCurrentModel() == "parakeet-v3"
    assert svc.changed == ["parakeet-v3"], "the GNOME extension refreshes on ModelChanged"


def test_a_stopped_service_falls_back_to_the_settings(svc):
    svc.NotifyRunningEngine("small", "cpu")
    svc.clear_running_engine()
    assert svc.GetCurrentModel() == "parakeet-v3" and svc.GetDeviceType() == "vulkan"


def test_the_service_records_every_load_path():
    """Each "Model loaded" point records the engine, and main reports it."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "src" / "talktype" / "app.py").read_text()
    assert src.count("_record_engine(") >= 5        # def + 4 load points
    assert "_notify_tray_running_engine()" in src

"""Performance presets and the Vulkan graphics route (whisper_vulkan.py).

The GPU presets (Balanced, Quality, Most Accurate) were written for CUDA only:
"Most Accurate" refused to run without CUDA, and someone set up for Vulkan who
picked Balanced or Quality was quietly moved to the processor, because the
preset saw no CUDA libraries and saved device=cpu.
"""
from types import SimpleNamespace

import pytest

from talktype import config as C
from talktype import vulkan_setup_dialogs as vsd
from talktype import whisper_vulkan as wv
from talktype.tray import DictationTray


@pytest.fixture
def env(monkeypatch):
    """A stand-in tray plus switches for every outside dependency."""
    state = SimpleNamespace(
        device="cpu", cuda=False, nvidia=False, vulkan_offered=True,
        vulkan_installed=set(), fw_cached=set(), chooser=None, setup_ok=True,
        files_ok=True, message_answer=None, saved=[], calls=[])

    def load():
        return SimpleNamespace(model="small", device=state.device,
                               auto_timeout_enabled=True, auto_timeout_minutes=5)

    def save(cfg):
        state.saved.append((cfg.model, cfg.device))

    monkeypatch.setattr(C, "load_config", load)
    monkeypatch.setattr(C, "save_config", save)
    monkeypatch.setattr("talktype.cuda_helper.has_talktype_cuda_libraries", lambda: state.cuda)
    monkeypatch.setattr("talktype.cuda_helper.detect_nvidia_gpu", lambda: state.nvidia)
    monkeypatch.setattr(wv, "is_offered", lambda: state.vulkan_offered)
    monkeypatch.setattr(wv, "is_installed", lambda m: m in state.vulkan_installed)
    monkeypatch.setattr("talktype.model_helper.is_model_cached_fast", lambda m: m in state.fw_cached)
    monkeypatch.setattr("talktype.model_helper.download_model_with_progress",
                        lambda *a, **k: state.calls.append(("fw-download", a[0])) or "model")
    monkeypatch.setattr(vsd, "choose_light_or_full", lambda parent, model:
                        state.calls.append(("chooser", model)) or state.chooser)
    monkeypatch.setattr(vsd, "set_up", lambda parent, model, confirm=True:
                        state.calls.append(("vulkan-setup", model)) or state.setup_ok)
    monkeypatch.setattr(vsd, "ensure_files", lambda parent, model, confirm:
                        state.calls.append(("vulkan-files", model)) or state.files_ok)
    monkeypatch.setattr(vsd, "message", lambda parent, kind, title, text, buttons=None:
                        state.calls.append(("message", title)) or state.message_answer)
    monkeypatch.setattr("talktype.app._notify", lambda *a: None)

    tray = SimpleNamespace(
        PERFORMANCE_PRESETS=DictationTray.PERFORMANCE_PRESETS,
        _PRESET_EXTRA_KEYS=DictationTray._PRESET_EXTRA_KEYS,
        preset_radios={}, _updating_preset=False)
    tray._get_current_preset = lambda: "custom"
    tray._revert_preset_radio = lambda: state.calls.append(("revert",))
    tray._download_cuda_for_most_accurate = lambda: state.calls.append(("cuda-download",))
    tray.update_menu_display = lambda *a: None
    tray._emit_model_changed = lambda m: None
    tray.restart_service = lambda _x: state.calls.append(("restart",))
    state.apply = lambda preset: DictationTray.set_performance_preset(tray, preset)
    return state


def test_a_vulkan_user_keeps_vulkan_for_every_gpu_preset(env):
    env.device = "vulkan"
    env.vulkan_installed = {"small", "medium", "large-v3"}
    for preset, model in (("balanced", "small"), ("quality", "medium"), ("accurate", "large-v3")):
        env.saved.clear()
        env.apply(preset)
        assert env.saved == [(model, "vulkan")]
    assert not [c for c in env.calls if c[0] in ("fw-download", "chooser", "cuda-download")]


def test_a_vulkan_user_gets_the_vulkan_model_downloaded_not_faster_whispers(env):
    env.device = "vulkan"
    env.apply("quality")
    assert ("vulkan-files", "medium") in env.calls
    assert not [c for c in env.calls if c[0] == "fw-download"]
    assert env.saved == [("medium", "vulkan")]


def test_a_cancelled_vulkan_model_download_changes_nothing(env):
    env.device, env.files_ok = "vulkan", False
    env.apply("accurate")
    assert env.saved == [] and ("revert",) in env.calls


def test_nvidia_without_cuda_can_take_the_light_route(env):
    env.nvidia, env.chooser = True, vsd.LIGHT
    env.vulkan_installed = {"large-v3"}
    env.apply("accurate")
    assert ("chooser", "large-v3") in env.calls and ("vulkan-setup", "large-v3") in env.calls
    assert env.saved == [("large-v3", "vulkan")] and ("restart",) in env.calls


def test_nvidia_without_cuda_can_still_take_the_full_route(env):
    env.nvidia, env.chooser = True, vsd.FULL
    env.apply("accurate")
    assert ("cuda-download",) in env.calls and env.saved == []


def test_cancelling_the_choice_changes_nothing(env):
    env.nvidia, env.chooser = True, None
    env.apply("accurate")
    assert env.saved == [] and ("vulkan-setup", "large-v3") not in env.calls


def test_a_light_setup_that_fails_the_speed_check_changes_nothing(env):
    env.nvidia, env.chooser, env.setup_ok = True, vsd.LIGHT, False
    env.apply("accurate")
    assert env.saved == []


def test_amd_or_intel_graphics_get_offered_vulkan(env):
    from gi.repository import Gtk
    env.message_answer = Gtk.ResponseType.OK
    env.vulkan_installed = {"large-v3"}
    env.apply("accurate")
    assert ("message", "Set up 'Most Accurate'?") in env.calls
    assert env.saved == [("large-v3", "vulkan")]


def test_no_graphics_card_at_all_is_told_plainly(env):
    env.vulkan_offered = False
    env.apply("accurate")
    assert ("message", "Cannot Apply 'Most Accurate' Preset") in env.calls
    assert env.saved == []


def test_cuda_users_are_unaffected(env):
    env.device, env.cuda = "cuda", True
    env.fw_cached = {"large-v3"}
    env.apply("accurate")
    assert env.saved == [("large-v3", "cuda")]
    assert not [c for c in env.calls if c[0] in ("chooser", "vulkan-setup", "vulkan-files")]


def test_a_vulkan_user_keeps_vulkan_for_fast_and_accurate(env):
    """Parakeet runs on the graphics chip through Vulkan too, so picking
    Fast & Accurate no longer moves a Vulkan user to the processor."""
    env.device = "vulkan"
    env.vulkan_installed = {"parakeet-v3"}
    env.apply("parakeet")
    assert env.saved == [("parakeet-v3", "vulkan")]
    assert not [c for c in env.calls if c[0] == "fw-download"]


def test_fast_and_accurate_on_vulkan_downloads_parakeets_graphics_file(env):
    env.device = "vulkan"
    env.apply("parakeet")
    assert ("vulkan-files", "parakeet-v3") in env.calls
    assert env.saved == [("parakeet-v3", "vulkan")]


def test_fast_and_accurate_without_vulkan_stays_on_the_processor(env):
    env.fw_cached = {"parakeet-v3"}
    env.apply("parakeet")
    assert env.saved == [("parakeet-v3", "cpu")]
    assert not [c for c in env.calls if c[0].startswith("vulkan")]

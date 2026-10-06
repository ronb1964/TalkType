"""The tray's Performance menu: three outcome presets from recommend.py.

Seven model-named presets used to promise "GPU" and silently use the
processor. Now Recommended for this computer / Lightest / Battery saver come
from recommend.presets(), so the menu, first run and the GNOME menu agree.
"""
import types

import pytest

from talktype import recommend as r
from talktype import tray as tray_mod

NVIDIA = r.Hardware("NVIDIA GeForce RTX 4070 SUPER", has_nvidia=True)


class FakeTray:
    _current_presets = tray_mod.DictationTray._current_presets
    _get_current_preset = tray_mod.DictationTray._get_current_preset
    set_performance_preset = tray_mod.DictationTray.set_performance_preset

    def __init__(self):
        self.reverted = 0
        self.restarted = 0
        self.preset_radios = {}

    def _revert_preset_radio(self):
        self.reverted += 1

    def update_menu_display(self, is_running=None):
        pass

    def _emit_model_changed(self, model):
        pass

    def restart_service(self, _):
        self.restarted += 1


@pytest.fixture
def env(monkeypatch):
    cfg = types.SimpleNamespace(model="small", device="cpu", auto_timeout_enabled=True,
                                auto_timeout_minutes=5, dictation_language="en",
                                language_mode="auto", language="", vulkan_slower=False)
    saved = []
    monkeypatch.setattr("talktype.config.load_config", lambda: cfg)
    monkeypatch.setattr("talktype.config.save_config", lambda c: saved.append((c.model, c.device)))
    monkeypatch.setattr(r, "detect_hardware", lambda cfg=None: NVIDIA)
    monkeypatch.setattr("talktype.model_helper.is_model_cached_fast", lambda m: True)
    monkeypatch.setattr("talktype.app._notify", lambda t, b: None)
    monkeypatch.setattr("talktype.whisper_vulkan.is_offered", lambda: True)
    return cfg, saved


def test_three_presets_in_order(env):
    assert [p.id for p in FakeTray()._current_presets()] == ["recommended", "lightest", "battery"]


def test_recommended_runs_the_vulkan_setup_then_saves(env, monkeypatch):
    cfg, saved = env
    calls = []
    monkeypatch.setattr("talktype.vulkan_setup_dialogs.ensure_files",
                        lambda p, m, confirm: calls.append(("files", m)) or True)
    monkeypatch.setattr("talktype.vulkan_setup_dialogs.run_speed_check",
                        lambda p, m: calls.append(("speed", m)) or True)
    t = FakeTray()
    t.set_performance_preset("recommended")
    assert calls == [("files", "parakeet-v3"), ("speed", "parakeet-v3")]
    assert saved == [("parakeet-v3", "vulkan")] and t.restarted == 1


def test_recommended_falls_back_to_the_processor_when_it_is_faster(env, monkeypatch):
    cfg, saved = env
    monkeypatch.setattr("talktype.vulkan_setup_dialogs.ensure_files", lambda p, m, confirm: True)
    monkeypatch.setattr("talktype.vulkan_setup_dialogs.run_speed_check", lambda p, m: False)
    FakeTray().set_performance_preset("recommended")
    assert saved == [("parakeet-v3", "cpu")]


def test_cancelling_the_download_changes_nothing(env, monkeypatch):
    """Review focus 4."""
    cfg, saved = env
    monkeypatch.setattr("talktype.vulkan_setup_dialogs.ensure_files", lambda p, m, confirm: False)
    t = FakeTray()
    t.set_performance_preset("recommended")
    assert saved == [] and t.reverted == 1 and t.restarted == 0


def test_battery_saver_sets_its_timeout(env):
    cfg, saved = env
    FakeTray().set_performance_preset("battery")
    assert saved == [("tiny", "cpu")]
    assert (cfg.auto_timeout_enabled, cfg.auto_timeout_minutes) == (True, 2)


@pytest.mark.parametrize("old_id", ["balanced", "accurate", "parakeet", "fastest", "custom"])
def test_old_or_unknown_ids_are_ignored(env, old_id):
    """Review focus 3: an older GNOME extension sends the old ids."""
    cfg, saved = env
    t = FakeTray()
    t.set_performance_preset(old_id)
    assert saved == [] and t.restarted == 0


def test_current_preset_uses_match_preset(env):
    cfg, _ = env
    cfg.model, cfg.device = "parakeet-v3", "vulkan"
    assert FakeTray()._get_current_preset() == "recommended"
    cfg.model, cfg.device = "medium", "cuda"
    assert FakeTray()._get_current_preset() == "custom"


def test_dbus_exposes_presets_and_the_active_one():
    from talktype.dbus_service import TalkTypeDBusService
    svc = TalkTypeDBusService.__new__(TalkTypeDBusService)
    svc.running_engine = None
    svc.claimed_hotkeys = []
    svc.app = types.SimpleNamespace(
        get_presets=lambda: [("recommended", "Recommended for this computer", "x")],
        current_preset=lambda: "recommended",
        config=types.SimpleNamespace(model="parakeet-v3", device="vulkan",
                                     auto_timeout_enabled=True, auto_timeout_minutes=5),
        is_recording=False, service_running=True)
    svc.IsRecording = lambda: False
    svc.IsServiceRunning = lambda: True
    svc.GetInjectionMode = lambda: "auto"
    assert list(svc.GetPresets()) == [("recommended", "Recommended for this computer", "x")]
    assert svc.GetStatus()["preset"] == "recommended"


def test_old_preset_table_is_gone():
    src = (tray_mod.__file__)
    text = open(src).read()
    assert "PERFORMANCE_PRESETS" not in text and "_download_cuda_for_most_accurate" not in text

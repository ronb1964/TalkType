"""After the welcome card, setup downloads exactly what it showed."""
import types

import pytest

from talktype import welcome_dialog as wd


@pytest.fixture
def env(monkeypatch):
    cfg = types.SimpleNamespace(model="parakeet-v3", device="cpu", dictation_language="",
                                recommend_notice_shown=False)
    calls = []
    monkeypatch.setattr("talktype.config.load_config", lambda: cfg)
    monkeypatch.setattr("talktype.config.save_config", lambda c: calls.append(("save", c.model, c.device)))
    monkeypatch.setattr(wd, "_setup_vulkan_engine_first_run", lambda: calls.append(("engine",)))
    monkeypatch.setattr(wd, "_download_vulkan_model_first_run", lambda m: calls.append(("vk", m)) or True)
    monkeypatch.setattr(wd, "_vulkan_speed_check_first_run", lambda m: calls.append(("speed", m)) or True)
    monkeypatch.setattr("talktype.model_helper.is_model_cached", lambda m: False)
    monkeypatch.setattr("talktype.model_helper.download_model_with_progress",
                        lambda m, **k: calls.append(("cpu", m)) or object())
    return cfg, calls


def test_graphics_card_setup(env):
    cfg, calls = env
    wd._apply_first_run_setup({"model": "parakeet-v3", "device": "vulkan", "dictation_language": "en"})
    assert ("engine",) in calls and ("vk", "parakeet-v3") in calls and ("speed", "parakeet-v3") in calls
    assert (cfg.model, cfg.device, cfg.dictation_language) == ("parakeet-v3", "vulkan", "en")
    assert cfg.recommend_notice_shown is True
    assert not any(c[0] == "cpu" for c in calls)


def test_slower_graphics_falls_back_to_the_processor_model(env, monkeypatch):
    cfg, calls = env
    monkeypatch.setattr(wd, "_vulkan_speed_check_first_run", lambda m: False)
    wd._apply_first_run_setup({"model": "parakeet-v3", "device": "vulkan", "dictation_language": "en"})
    assert cfg.device == "cpu" and ("cpu", "parakeet-v3") in calls


def test_processor_setup(env):
    cfg, calls = env
    wd._apply_first_run_setup({"model": "small", "device": "cpu", "dictation_language": "ja"})
    assert ("cpu", "small") in calls and not any(c[0] in ("engine", "vk") for c in calls)
    assert (cfg.model, cfg.device, cfg.dictation_language) == ("small", "cpu", "ja")


def test_tips_dialog_no_longer_picks_a_model():
    import pathlib
    src = pathlib.Path(wd.__file__).read_text()
    assert "Choose Your Starting Model" not in src

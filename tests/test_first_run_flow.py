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
    monkeypatch.setattr(wd, "_setup_vulkan_engine_first_run", lambda: calls.append(("engine",)), raising=False)
    monkeypatch.setattr(wd, "_download_vulkan_model_first_run", lambda m: calls.append(("vk", m)) or True)
    monkeypatch.setattr(wd, "_vulkan_speed_check_first_run", lambda m: calls.append(("speed", m)) or True)
    monkeypatch.setattr("talktype.model_helper.is_model_cached_fast", lambda m: False)
    monkeypatch.setattr("talktype.model_helper.download_model_with_progress",
                        lambda m, **k: calls.append(("cpu", m)) or object())
    return cfg, calls


def test_graphics_card_setup(env):
    """One download window: the model's own window fetches the engine too.
    A separate engine window first meant two windows, and on a dead network
    the engine was tried twice (review minor)."""
    cfg, calls = env
    wd._apply_first_run_setup({"model": "parakeet-v3", "device": "vulkan", "dictation_language": "en"})
    assert ("engine",) not in calls
    assert ("vk", "parakeet-v3") in calls and ("speed", "parakeet-v3") in calls
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


@pytest.fixture
def store(monkeypatch):
    """Like the real config: every load is a fresh copy and every save writes
    all of it back. The shared-object fixture above hid a lost write."""
    saved = {"model": "parakeet-v3", "device": "cpu", "dictation_language": "",
             "recommend_notice_shown": False, "vulkan_slower": False}
    calls = []
    monkeypatch.setattr("talktype.config.load_config", lambda: types.SimpleNamespace(**saved))
    monkeypatch.setattr("talktype.config.save_config", lambda c: saved.update(vars(c)))
    monkeypatch.setattr(wd, "_download_vulkan_model_first_run", lambda m: True)
    monkeypatch.setattr("talktype.model_helper.is_model_cached_fast", lambda m: False)
    monkeypatch.setattr("talktype.model_helper.download_model_with_progress",
                        lambda m, **k: calls.append(m) or object())
    return saved, calls


def _processor_wins(monkeypatch):
    """The real speed check records the loss in its own load/save."""
    from talktype.config import load_config, save_config

    def check(model):
        cfg = load_config()
        cfg.vulkan_slower = True
        save_config(cfg)
        return False
    monkeypatch.setattr(wd, "_vulkan_speed_check_first_run", check)


def test_a_lost_speed_check_stays_remembered(store, monkeypatch):
    saved, calls = store
    _processor_wins(monkeypatch)
    wd._apply_first_run_setup({"model": "parakeet-v3", "device": "vulkan", "dictation_language": "en"})
    assert saved["vulkan_slower"] is True
    assert (saved["model"], saved["device"]) == ("parakeet-v3", "cpu")


def test_large_v3_becomes_small_when_it_ends_up_on_the_processor(store, monkeypatch):
    """Large-v3 on the processor is the setup the card greys out ("Needs a
    graphics card"), and first run would have fetched 3 GB of it unasked."""
    saved, calls = store
    _processor_wins(monkeypatch)
    wd._apply_first_run_setup({"model": "large-v3", "device": "vulkan", "dictation_language": "ja"})
    assert (saved["model"], saved["device"]) == ("small", "cpu")
    assert calls == ["small"]


def test_failed_graphics_download_also_falls_back_to_small(store, monkeypatch):
    saved, calls = store
    monkeypatch.setattr(wd, "_download_vulkan_model_first_run", lambda m: False)
    monkeypatch.setattr(wd, "_vulkan_speed_check_first_run", lambda m: True)
    wd._apply_first_run_setup({"model": "large-v3", "device": "vulkan", "dictation_language": "ja"})
    assert (saved["model"], saved["device"]) == ("small", "cpu")
    assert calls == ["small"]

"""After the welcome card, setup downloads exactly what it showed."""
import types

import pytest

from tuxtalk import welcome_dialog as wd


@pytest.fixture
def env(monkeypatch):
    cfg = types.SimpleNamespace(model="parakeet-v3", device="cpu", dictation_language="",
                                recommend_notice_shown=False)
    calls = []
    monkeypatch.setattr("tuxtalk.config.load_config", lambda: cfg)
    monkeypatch.setattr("tuxtalk.config.save_config", lambda c: calls.append(("save", c.model, c.device)))
    monkeypatch.setattr(wd, "_setup_vulkan_engine_first_run", lambda: calls.append(("engine",)), raising=False)
    monkeypatch.setattr(wd, "_download_vulkan_model_first_run", lambda m, **k: calls.append(("vk", m)) or True)
    monkeypatch.setattr(wd, "_vulkan_speed_check_first_run", lambda m: calls.append(("speed", m)) or True)
    monkeypatch.setattr("tuxtalk.model_helper.is_model_cached_fast", lambda m: False)
    monkeypatch.setattr("tuxtalk.model_helper.download_model_with_progress",
                        lambda m, **k: calls.append(("cpu", m)) or object())
    return cfg, calls


def test_graphics_card_setup(env):
    """One download window: the model's own window fetches the engine too, so
    there is no second window and a dead network is tried only once."""
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
    all of it back, so a lost write shows (the shared-object fixture above
    would hide one)."""
    saved = {"model": "parakeet-v3", "device": "cpu", "dictation_language": "",
             "recommend_notice_shown": False, "vulkan_slower": False}
    calls = []
    monkeypatch.setattr("tuxtalk.config.load_config", lambda: types.SimpleNamespace(**saved))
    monkeypatch.setattr("tuxtalk.config.save_config", lambda c: saved.update(vars(c)))
    monkeypatch.setattr(wd, "_download_vulkan_model_first_run", lambda m, **k: True)
    monkeypatch.setattr("tuxtalk.model_helper.is_model_cached_fast", lambda m: False)
    monkeypatch.setattr("tuxtalk.model_helper.download_model_with_progress",
                        lambda m, **k: calls.append(m) or object())
    return saved, calls


def _processor_wins(monkeypatch):
    """The real speed check records the loss in its own load/save."""
    from tuxtalk.config import load_config, save_config

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
    graphics card"), and first run must not fetch 3 GB of it unasked."""
    saved, calls = store
    _processor_wins(monkeypatch)
    wd._apply_first_run_setup({"model": "large-v3", "device": "vulkan", "dictation_language": "ja"})
    assert (saved["model"], saved["device"]) == ("small", "cpu")
    assert calls == ["small"]


def test_failed_graphics_download_also_falls_back_to_small(store, monkeypatch):
    saved, calls = store
    monkeypatch.setattr(wd, "_download_vulkan_model_first_run", lambda m, **k: False)
    monkeypatch.setattr(wd, "_vulkan_speed_check_first_run", lambda m: True)
    wd._apply_first_run_setup({"model": "large-v3", "device": "vulkan", "dictation_language": "ja"})
    assert (saved["model"], saved["device"]) == ("small", "cpu")
    assert calls == ["small"]


def test_a_cancelled_first_run_download_starts_no_other(store, monkeypatch):
    """One Cancel is enough: it must not go on to Whisper Small, then Tiny."""
    saved, calls = store

    def cancelled(m, result_info=None, **k):
        calls.append(m)
        result_info["cancelled"] = True
        return None

    monkeypatch.setattr("tuxtalk.model_helper.download_model_with_progress", cancelled)
    wd._apply_first_run_setup({"model": "parakeet-v3", "device": "cpu", "dictation_language": "en"})
    assert calls == ["parakeet-v3"]
    assert saved["model"] == "parakeet-v3"     # offered again when the service starts


def test_a_cancelled_graphics_download_starts_no_processor_download(store, monkeypatch):
    """Cancel in the graphics download window must not go straight on to a
    processor download of the same model."""
    saved, calls = store
    speed = []

    def cancelled(m, result_info=None):
        result_info["cancelled"] = True
        return False

    monkeypatch.setattr(wd, "_download_vulkan_model_first_run", cancelled)
    monkeypatch.setattr(wd, "_vulkan_speed_check_first_run", lambda m: speed.append(m) or True)
    wd._apply_first_run_setup({"model": "parakeet-v3", "device": "vulkan", "dictation_language": "en"})
    assert calls == [] and speed == []
    assert (saved["model"], saved["device"]) == ("parakeet-v3", "cpu")   # offered when the service starts


def test_a_failed_first_run_download_tries_one_smaller_model(store, monkeypatch):
    saved, calls = store
    monkeypatch.setattr("tuxtalk.model_helper.download_model_with_progress",
                        lambda m, **k: calls.append(m) or None)
    wd._apply_first_run_setup({"model": "parakeet-v3", "device": "cpu", "dictation_language": "en"})
    assert calls == ["parakeet-v3", "small"]   # not a third error box for tiny


def test_a_failed_download_uses_an_already_downloaded_smaller_model(store, monkeypatch):
    saved, calls = store
    monkeypatch.setattr("tuxtalk.model_helper.is_model_cached_fast", lambda m: m == "tiny")
    monkeypatch.setattr("tuxtalk.model_helper.download_model_with_progress",
                        lambda m, **k: calls.append(m) or None)
    wd._apply_first_run_setup({"model": "parakeet-v3", "device": "cpu", "dictation_language": "en"})
    assert calls == ["parakeet-v3"] and saved["model"] == "tiny"


def test_the_emergency_fallback_also_moves_to_the_processor(store, monkeypatch):
    """whisper.cpp has no copy of Tiny, so vulkan + tiny would not run."""
    saved, calls = store

    def broken(m, **k):
        raise RuntimeError("engine check failed")

    monkeypatch.setattr(wd, "_download_vulkan_model_first_run", broken)
    monkeypatch.setattr("tuxtalk.model_helper.is_model_cached_fast", lambda m: m == "tiny")
    wd._apply_first_run_setup({"model": "parakeet-v3", "device": "vulkan", "dictation_language": "en"})
    assert (saved["model"], saved["device"]) == ("tiny", "cpu")


def test_model_download_reports_a_cancel(monkeypatch):
    from tuxtalk import model_helper as mh
    monkeypatch.setattr(mh, "is_model_cached_fast", lambda m: False)

    class Declined:
        def format_secondary_text(self, text):
            pass

        def set_position(self, pos):
            pass

        def run(self):
            return mh.Gtk.ResponseType.CANCEL

        def destroy(self):
            pass

    monkeypatch.setattr(mh, "message_dialog", lambda **k: Declined())
    info = {}
    assert mh.download_model_with_progress("small", result_info=info) is None
    assert info == {"cancelled": True}


def test_the_ready_screen_names_the_key_the_user_chose(monkeypatch):
    """Not always F8: the hotkey test may have changed the key."""
    monkeypatch.setattr("tuxtalk.config.load_config",
                        lambda: types.SimpleNamespace(hotkey="F10"))
    assert wd._saved_hold_key() == "F10"
    monkeypatch.setattr("tuxtalk.config.load_config",
                        lambda: types.SimpleNamespace(hotkey=""))
    assert wd._saved_hold_key() == "F8"
    import pathlib
    src = pathlib.Path(wd.__file__).read_text()
    assert "Press and hold <b>F8</b> (or your hotkey)" not in src

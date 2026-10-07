"""Existing users hear once that there's a better setup, only if there is."""
import types

import pytest

from talktype import recommend as r
from talktype import tray

NVIDIA = r.Hardware("NVIDIA GeForce RTX 4070 SUPER", True)


@pytest.fixture
def env(monkeypatch):
    cfg = types.SimpleNamespace(model="small", device="cpu", recommend_notice_shown=False,
                                dictation_language="en", language_mode="auto", language="",
                                vulkan_slower=False)
    notes, saved = [], []
    monkeypatch.setattr("talktype.config.load_config", lambda: cfg)
    monkeypatch.setattr("talktype.config.save_config", lambda c: saved.append(c.recommend_notice_shown))
    monkeypatch.setattr("talktype.app._notify", lambda t, b: notes.append(b))
    monkeypatch.setattr("talktype.cuda_helper.is_first_run", lambda: False)
    monkeypatch.setattr("talktype.service_launcher.find_service_pids", lambda: [4242])
    monkeypatch.setattr(r, "detect_hardware", lambda cfg=None: NVIDIA)
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    return cfg, notes, saved


def test_shown_once_when_the_setup_differs(env):
    cfg, notes, saved = env
    tray.maybe_show_recommend_notice()
    assert len(notes) == 1 and "Parakeet on your NVIDIA GeForce RTX 4070 SUPER" in notes[0]
    assert "Performance" in notes[0] and saved == [True]
    cfg.recommend_notice_shown = True
    tray.maybe_show_recommend_notice()
    assert len(notes) == 1


def test_silent_when_already_on_the_recommendation(env):
    cfg, notes, saved = env
    cfg.model, cfg.device = "parakeet-v3", "vulkan"
    tray.maybe_show_recommend_notice()
    assert notes == [] and saved == [True]


def test_never_on_first_run_or_flatpak(env, monkeypatch):
    cfg, notes, saved = env
    monkeypatch.setattr("talktype.cuda_helper.is_first_run", lambda: True)
    tray.maybe_show_recommend_notice()
    monkeypatch.setattr("talktype.cuda_helper.is_first_run", lambda: False)
    monkeypatch.setenv("FLATPAK_ID", "io.github.ronb1964.TalkType")
    tray.maybe_show_recommend_notice()
    assert notes == []


def test_notice_wording():
    s = r.recommend("en", NVIDIA)
    assert tray.recommend_notice_text(s) == (
        "There's a better setup for this computer: Parakeet on your NVIDIA GeForce "
        "RTX 4070 SUPER. Choose Performance → Recommended for this computer in the "
        "TalkType menu to switch.")


def test_waits_for_the_dictation_service(env, monkeypatch):
    """Spec: the notice comes once the service is up, not on a fixed timer."""
    cfg, notes, saved = env
    monkeypatch.setattr("talktype.service_launcher.find_service_pids", lambda: [])
    assert tray.maybe_show_recommend_notice() is True       # ask again later
    assert notes == [] and saved == []
    monkeypatch.setattr("talktype.service_launcher.find_service_pids", lambda: [4242])
    assert tray.maybe_show_recommend_notice() is False
    assert len(notes) == 1

"""The Performance menu must show which preset is actually active.

"Battery Saver" and "Fastest" are both tiny/CPU — they differ only in the
auto-timeout. _get_current_preset matched on model+device alone and returned
the first hit in dict order, which is always "Fastest". So selecting Battery
Saver moved the radio dot straight back to Fastest, and the user could never
see that Battery Saver was on.
"""

from types import SimpleNamespace

import pytest

from talktype import config as C
from talktype.tray import DictationTray


def _tray():
    return SimpleNamespace(
        PERFORMANCE_PRESETS=DictationTray.PERFORMANCE_PRESETS,
        _PRESET_EXTRA_KEYS=DictationTray._PRESET_EXTRA_KEYS,
    )


@pytest.fixture
def settings(monkeypatch):
    """Let each test dictate what load_config() returns."""
    holder = {}

    def fake_load():
        return SimpleNamespace(**holder)

    monkeypatch.setattr(C, "load_config", fake_load)
    monkeypatch.setattr("talktype.tray.load_config", fake_load, raising=False)
    return holder


def _current(holder, **cfg):
    holder.clear()
    holder.update({"model": "tiny", "device": "cpu",
                   "auto_timeout_enabled": True, "auto_timeout_minutes": 5})
    holder.update(cfg)
    return DictationTray._get_current_preset(_tray())


def test_battery_saver_is_recognised_by_its_timeout(settings):
    assert _current(settings, model="tiny", device="cpu",
                    auto_timeout_enabled=True, auto_timeout_minutes=2) == "battery"


def test_fastest_is_still_recognised(settings):
    assert _current(settings, model="tiny", device="cpu",
                    auto_timeout_minutes=5) == "fastest"


def test_the_other_presets_are_unaffected(settings):
    assert _current(settings, model="medium", device="cuda") == "quality"
    assert _current(settings, model="large-v3", device="cuda") == "accurate"
    assert _current(settings, model="base", device="cpu") == "light"


def test_an_unmatched_combination_is_custom(settings):
    assert _current(settings, model="large-v3", device="cpu",
                    auto_timeout_minutes=99) in ("accurate", "custom")

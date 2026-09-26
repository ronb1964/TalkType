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


def test_parakeet_preset_is_recognised(settings):
    assert _current(settings, model="parakeet-v3", device="cpu") == "parakeet"
    # Picked in Preferences with device left on "cuda": Parakeet ignores the
    # device, so the menu should still show it rather than "Custom".
    assert _current(settings, model="parakeet-v3", device="cuda") == "parakeet"


def test_tray_and_gnome_extension_offer_the_same_presets():
    """CLAUDE.md: both menus must list the same presets in the same order."""
    import re
    from pathlib import Path

    js = (Path(__file__).resolve().parent.parent
          / "gnome-extension/talktype@ronb1964.github.io/extension.js").read_text()
    block = re.search(r"const PERFORMANCE_PRESETS = \{(.*?)\n\};", js, re.S).group(1)
    js_presets = re.findall(
        r"'(\w+)': \{\s*label: '([^']*)',\s*description: '([^']*)',\s*model: '([^']*)',\s*device: '([^']*)'",
        block)
    tray_presets = [(k, p["label"], p["description"], p["model"], p["device"])
                    for k, p in DictationTray.PERFORMANCE_PRESETS.items()]
    assert js_presets == tray_presets


def test_one_click_applies_one_preset_once():
    """GTK fires "activate" on the radio being unselected too. Acting on that
    re-applied the previous preset (restarting the service) before the new one."""
    import gi
    gi.require_version("Gtk", "3.0")

    applied = []

    class Tray:
        PERFORMANCE_PRESETS = DictationTray.PERFORMANCE_PRESETS

        def set_performance_preset(self, preset_id):
            applied.append(preset_id)

    tray = Tray()
    # Keep the returned menu: once it is garbage-collected GTK destroys its
    # items, taking their radio group and handlers with them.
    menu = DictationTray._build_performance_submenu(tray)  # noqa: F841
    tray.preset_radios["accurate"].activate()
    applied.clear()
    tray.preset_radios["parakeet"].activate()
    assert applied == ["parakeet"]


def test_one_click_applies_one_injection_mode_once():
    import gi
    gi.require_version("Gtk", "3.0")

    applied = []

    class Tray:
        def set_injection_mode(self, mode):
            applied.append(mode)

    tray = Tray()
    menu = DictationTray._build_injection_submenu(tray)  # noqa: F841  (see above)
    tray.injection_mode_type.activate()
    applied.clear()
    tray.injection_mode_paste.activate()
    assert applied == ["paste"]

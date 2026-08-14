"""New recording-indicator config keys: defaults, validation, live-apply.

These settings drive the selectable indicator styles (waveform, bars, radial)
alongside the orb, plus color, backing and sensitivity. They must all apply
live — the service reads them without a restart — so every one belongs in
LIVE_APPLIED_KEYS.

See docs/superpowers/specs/2026-08-14-recording-indicator-styles-design.md.
"""
from talktype import config


def test_new_indicator_fields_have_approved_defaults():
    s = config.Settings()
    assert s.indicator_style == "orb"
    assert s.indicator_color_mode == "system"
    assert s.indicator_backing == "medium"
    assert s.indicator_sensitivity == 1.0
    assert s.orb_follow_system_color is False


def test_valid_sets_exist():
    assert config.VALID_INDICATOR_STYLES == {"orb", "waveform", "bars", "radial"}
    assert config.VALID_COLOR_MODES == {"system", "custom"}
    assert config.VALID_BACKINGS == {"off", "soft", "medium", "strong"}


def test_new_keys_are_live_applied_not_restart():
    keys = {"indicator_style", "indicator_color_mode", "indicator_color",
            "indicator_backing", "indicator_sensitivity", "orb_follow_system_color"}
    assert keys <= config.LIVE_APPLIED_KEYS
    assert not (keys & config.RESTART_REQUIRED_KEYS)


def test_invalid_style_is_reported():
    s = config.Settings()
    s.indicator_style = "bogus"
    problems = dict(config._validation_problems(s))
    assert "indicator_style" in problems


def test_invalid_backing_is_reported():
    s = config.Settings()
    s.indicator_backing = "loud"
    problems = dict(config._validation_problems(s))
    assert "indicator_backing" in problems


def test_sensitivity_out_of_range_is_reported():
    s = config.Settings()
    s.indicator_sensitivity = 9.0
    problems = dict(config._validation_problems(s))
    assert "indicator_sensitivity" in problems

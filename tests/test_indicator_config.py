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
    assert s.indicator_color_mode == "classic"   # orb looks like today out of the box
    assert s.indicator_backing == "medium"
    assert s.indicator_sensitivity == 1.0


def test_valid_sets_exist():
    assert config.VALID_INDICATOR_STYLES == {"orb", "waveform", "bars", "radial"}
    assert config.VALID_COLOR_MODES == {"classic", "system", "custom"}
    assert config.VALID_BACKINGS == {"off", "soft", "medium", "strong"}


def test_new_keys_are_live_applied_not_restart():
    keys = {"indicator_style", "indicator_color_mode", "indicator_color",
            "indicator_backing", "indicator_sensitivity"}
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


def test_float_sensitivity_round_trips_as_a_float():
    """A float field must survive save/reload as a float, not a string — the
    TOML writer had no float branch and the loader had no float caster, so
    indicator_sensitivity was the first float field to expose both."""
    assert config._toml_value(1.3) == "1.3"          # bare, not quoted
    assert config._TYPE_CASTERS["float"] is float     # loader casts it back

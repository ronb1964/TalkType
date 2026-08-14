"""Preferences exposes the new indicator controls and writes their config keys."""
import pathlib

PREFS = pathlib.Path(__file__).resolve().parent.parent / "src/talktype/prefs.py"


def test_controls_write_the_new_config_keys():
    text = PREFS.read_text()
    for key in ("indicator_style", "indicator_color_mode", "indicator_color",
                "indicator_backing", "indicator_sensitivity", "orb_follow_system_color"):
        assert key in text, f"Preferences never writes {key}"


def test_uses_american_spelling_for_color():
    text = PREFS.read_text()
    assert "Colour" not in text, "UI text must use American 'Color'"


def test_style_options_present():
    text = PREFS.read_text()
    for style in ("orb", "waveform", "bars", "radial"):
        assert style in text


def test_backing_options_present():
    text = PREFS.read_text()
    for level in ("off", "soft", "medium", "strong"):
        assert level in text

"""Preferences exposes the new indicator controls and writes their config keys."""
import pathlib

PREFS = pathlib.Path(__file__).resolve().parent.parent / "src/talktype/prefs.py"


def test_controls_write_the_new_config_keys():
    text = PREFS.read_text()
    for key in ("indicator_style", "indicator_color_mode", "indicator_color",
                "indicator_backing", "indicator_sensitivity"):
        assert key in text, f"Preferences never writes {key}"


def test_no_redundant_orb_checkbox():
    """The color dropdown governs the orb; the separate checkbox was confusing."""
    text = PREFS.read_text()
    assert "orb_follow_system_color" not in text


def test_color_dropdown_has_only_two_modes():
    """Two real choices remain: match the desktop accent, or pick a color.
    'Cyan' was a redundant third option and is gone (it lives on as the classic
    color you can pick from the swatch's preset palette)."""
    text = PREFS.read_text()
    assert '.append("system"' in text
    assert '.append("custom"' in text
    assert '.append("cyan"' not in text
    assert '"Cyan"' not in text
    assert "Classic cyan" not in text


def test_custom_color_selection_opens_the_picker():
    """Choosing 'Custom color' opens the picker immediately — no second click on
    a separate swatch. A guard stops the programmatic mode-flip from re-firing it."""
    text = PREFS.read_text()
    assert "_open_color_picker" in text
    assert "_suppress_color_popup" in text


def test_swatch_mirrors_the_desktop_accent_in_system_mode():
    """In system mode the swatch shows the live accent color — a continuity cue."""
    text = PREFS.read_text()
    assert "_sync_color_swatch" in text
    assert "theme_selected_bg_color" in text


def test_color_picker_seeds_a_preset_palette_with_classic_cyan_first():
    """The picker offers preset swatches so the classic cyan is one click away
    without knowing a hex code; it must be the first preset."""
    text = PREFS.read_text()
    assert "add_palette" in text
    assert "CLASSIC_CYAN_HEX" in text


def test_reset_to_classic_cyan_control_exists():
    """A plainly-labeled control snaps the color back to the classic cyan — the
    one color whose identity matters — without needing to know a hex code."""
    text = PREFS.read_text()
    assert "Reset to classic cyan" in text
    assert "_reset_color_to_classic" in text


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

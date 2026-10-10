"""The GNOME menu's Performance presets come from the tray (GetPresets).

The extension kept its own copy of the preset table and its own matcher, and
the two drifted (Battery Saver's dot sat on Fastest). Now it asks the tray.
"""
import json
import pathlib

EXT = pathlib.Path(__file__).resolve().parent.parent / "gnome-extension/talktype@ronb1964.github.io"
JS = (EXT / "extension.js").read_text()


def test_interface_declares_getpresets():
    assert '<method name="GetPresets">' in JS
    assert '<arg type="a(sss)" direction="out" name="presets"/>' in JS


def test_no_hard_coded_preset_table():
    assert "PERFORMANCE_PRESETS" not in JS and "PRESET_EXTRA_KEYS" not in JS
    assert "_getCurrentPreset" not in JS


def test_menu_is_built_from_the_tray():
    assert "GetPresetsRemote" in JS
    assert "status.preset" in JS


def test_version_is_16():
    """16: the Custom item (opens Preferences, shows the dot for custom settings)."""
    assert json.loads((EXT / "metadata.json").read_text())["version"] == 16


CUSTOM_LABEL = "Custom (opens Preferences)"


def test_both_menus_end_the_presets_with_the_same_custom_item():
    """The GTK tray had a greyed-out "Custom (via Preferences)" that did
    nothing, and the GNOME menu had no Custom item at all, so a custom setup
    showed no dot there. Both now offer it, and it opens Preferences."""
    tray = (EXT.parent.parent / "src/talktype/tray.py").read_text()
    assert f'"{CUSTOM_LABEL}"' in tray and "Custom (via Preferences)" not in tray
    assert f"'{CUSTOM_LABEL}'" in JS
    assert "this._presetItems['custom']" in JS


def test_gnome_custom_item_opens_preferences():
    start = JS.index(f"'{CUSTOM_LABEL}'")
    assert "OpenPreferencesRemote" in JS[start:start + 400]

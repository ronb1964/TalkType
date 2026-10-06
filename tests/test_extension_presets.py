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


def test_version_is_15():
    assert json.loads((EXT / "metadata.json").read_text())["version"] == 15

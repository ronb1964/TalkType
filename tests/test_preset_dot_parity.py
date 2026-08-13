"""Battery Saver must be able to show as the active preset in BOTH menus.

"Fastest" and "Battery Saver" are the same tiny/CPU pair — the only thing that
tells them apart is the auto-timeout. tray.py was fixed for this (the timeout is
part of the preset definition and matching runs most-specific-first), but the
GNOME extension kept its own copy of the preset table and its own matcher, which
compares model and device only. Since "fastest" is declared first, it always
won: choosing Battery Saver from the GNOME menu put the dot on Fastest and left
it there.

The extension gets its data from GetStatus over D-Bus, which did not expose the
timeout at all — so the extension could not have distinguished them even if it
tried. Both halves are covered here.
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXTENSION_DIR = ROOT / "gnome-extension/talktype@ronb1964.github.io"
EXTENSION_JS = EXTENSION_DIR / "extension.js"


def test_dbus_status_exposes_the_auto_timeout():
    """Without this the extension has nothing to tell the two presets apart."""
    text = (ROOT / "src/talktype/dbus_service.py").read_text()
    status_block = text.split("def GetStatus", 1)[1].split("def ", 1)[0]

    for field in ("auto_timeout_enabled", "auto_timeout_minutes"):
        assert field in status_block, (
            f"GetStatus does not report {field}, so the GNOME extension cannot "
            f"distinguish Battery Saver from Fastest — they are otherwise the "
            f"same tiny/CPU pair."
        )


def test_extension_battery_preset_declares_its_timeout():
    js = EXTENSION_JS.read_text()
    # Take the Battery Saver entry up to the end of its object literal, rather
    # than a fixed number of characters — the entry carries a comment
    # explaining why the timeout is there, and a short window missed it.
    after_label = js.split("label: 'Battery Saver'", 1)[1]
    battery_block = after_label.split("};", 1)[0]
    assert "auto_timeout" in battery_block, (
        "The extension's Battery Saver preset does not declare its timeout, so "
        "it stays indistinguishable from Fastest no matter what the matcher does."
    )


def test_extension_matches_most_specific_preset_first():
    """A plain model+device pass hands every tiny/CPU config to 'fastest'."""
    js = EXTENSION_JS.read_text()
    assert "_getCurrentPreset" in js, (
        "The preset matcher was renamed; this test is no longer checking it."
    )
    body = js.split("_getCurrentPreset", 1)[1].split("\n    _", 1)[0]
    assert "PRESET_EXTRA_KEYS" in body, (
        "_getCurrentPreset compares model and device only, so Battery Saver can "
        "never be reported as active — 'fastest' is declared first and claims "
        "every tiny/CPU configuration."
    )


def test_extension_version_bumped_for_these_changes():
    """The in-app updater compares this integer and nothing else.

    extension.js is changing here, so the version must move or existing GNOME
    users are told they are up to date and never receive the fix.
    """
    metadata = json.loads((EXTENSION_DIR / "metadata.json").read_text())
    assert metadata["version"] >= 7, (
        f"extension.js changed but metadata version is still "
        f"{metadata['version']}. Existing installs will never be offered it."
    )

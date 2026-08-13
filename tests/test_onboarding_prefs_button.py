"""The Open Preferences button belongs on the FINAL screen, not mid-onboarding.

Onboarding order (show_welcome_and_install):

    welcome → optional downloads → hotkey test
        → show_tips_and_features_dialog   ("You're All Set!", picks the model)
        → the model actually downloads
        → show_setup_complete_dialog      ("Ready!", the last thing shown)

The button was first added to the tips screen, which is wrong: at that point the
user has not yet chosen a model or downloaded it, so sending them into
Preferences interrupts setup halfway. The last screen is where they are done and
genuinely choosing what to do next — start dictating, or go and adjust settings.

These tests pin the placement so it cannot drift back.
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WELCOME = ROOT / "src/talktype/welcome_dialog.py"


def _function_source(name):
    """Return the source of a top-level function, up to the next one."""
    text = WELCOME.read_text()
    marker = f"\ndef {name}("
    assert marker in text, f"{name}() not found in welcome_dialog.py"
    body = text.split(marker, 1)[1]
    # Stop at the next top-level def so we do not bleed into the next screen.
    return body.split("\ndef ", 1)[0]


def test_final_screen_offers_preferences():
    body = _function_source("show_setup_complete_dialog")
    assert "Open Preferences" in body, (
        "The final 'Ready!' screen has no Open Preferences button. That is the "
        "one moment the user is finished and choosing what to do next."
    )


def test_mid_onboarding_screen_does_not_offer_preferences():
    body = _function_source("show_tips_and_features_dialog")
    assert "Open Preferences" not in body, (
        "The model-picker screen offers Open Preferences. Setup is not finished "
        "there — the model has not been chosen or downloaded yet, so this sends "
        "the user away mid-flow."
    )


def test_preferences_launcher_handles_appimage_and_dev():
    """A dev-only launcher would silently do nothing inside the AppImage."""
    text = WELCOME.read_text()
    launcher = text.split("def _open_preferences", 1)
    assert len(launcher) > 1, "Expected a shared _open_preferences() helper"
    body = launcher[1].split("\ndef ", 1)[0]
    assert "dictate-prefs" in body, (
        "The launcher does not try the AppImage's bin/dictate-prefs, so the "
        "button would do nothing for AppImage users."
    )
    assert "talktype.prefs" in body, (
        "The launcher has no dev-mode fallback (python -m talktype.prefs)."
    )

"""The Open Preferences button belongs on the FINAL screen, not mid-onboarding.

Onboarding order (show_welcome_and_install):

    welcome (chooses the setup) → optional downloads → hotkey test
        → the model actually downloads
        → show_setup_complete_dialog      ("Ready!", the last thing shown)

Before the model is downloaded, sending the user into Preferences would
interrupt setup halfway. The last screen is where they are done and genuinely
choosing what to do next — start dictating, or go and adjust settings.
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WELCOME = ROOT / "src/tuxtalk/welcome_dialog.py"


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


def test_nothing_says_ready_before_the_model_is_downloaded():
    """"You're All Set!" came before the download, so the first dictation
    couldn't work yet (Codex, 0.16 simplicity review). Setup Complete, after
    the download, is the one finish screen."""
    text = WELCOME.read_text()
    assert "show_tips_and_features_dialog" not in text
    flow = _function_source("show_welcome_and_install")
    assert flow.index("_apply_first_run_setup(result)") < flow.index("show_setup_complete_dialog(")


def test_preferences_launcher_is_the_shared_one():
    """It must start Preferences the way the tray does, in every install."""
    text = WELCOME.read_text()
    launcher = text.split("def _open_preferences", 1)
    assert len(launcher) > 1, "Expected a shared _open_preferences() helper"
    body = launcher[1].split("\ndef ", 1)[0]
    assert "launch_preferences" in body, (
        "The launcher does not use service_launcher.launch_preferences, so it "
        "can drift from how the tray opens Preferences."
    )

"""Which keys the first-run hotkey test accepts, reports and saves.

- Change Key took any key (Pause, Scroll_Lock, space, a letter) and said
  "Working!", but the service understands only F-keys and letters, so the
  app ended up with no hotkey; a letter started dictation while typing.
- Closing the test with the window's X saved nothing, and the settings start
  with no hotkey, so the service watched no key at all.
- The evdev reader passed on presses only, and only a release marks a key as
  working, so a key the compositor grabbed never tested as working.
"""
from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
from tuxtalk import welcome_dialog as wd  # noqa: E402


@pytest.mark.parametrize("key", ["Pause", "Scroll_Lock", "space", "a", "Shift_L", "KP_0", "F13"])
def test_keys_the_service_cannot_use_are_refused(key):
    assert wd._captured_key_problem(key, "F9")


def test_function_keys_are_accepted():
    assert wd._captured_key_problem("F10", "F9") is None


def test_both_hotkeys_cannot_be_the_same_key():
    assert "other hotkey" in wd._captured_key_problem("F9", "F9")


def _config(hold="", toggle=""):
    return SimpleNamespace(hotkey=hold, toggle_hotkey=toggle)


def test_closing_with_the_x_on_first_run_saves_the_shown_keys():
    assert wd._hotkeys_to_save(_config(), "F8", "F9", confirmed=False) == ("F8", "F9")


def test_closing_with_the_x_keeps_keys_already_saved():
    assert wd._hotkeys_to_save(_config("F6", "F7"), "F10", "F11", confirmed=False) == ("F6", "F7")


def test_continue_saves_the_chosen_keys():
    assert wd._hotkeys_to_save(_config("F6", "F7"), "F10", "F11", confirmed=True) == ("F10", "F11")


def test_an_unusable_saved_key_falls_back_to_the_defaults():
    assert wd._hotkeys_to_save(_config("Pause", "Pause"), "Pause", "Pause",
                               confirmed=False) == ("F8", "F9")


MODS = {56, 100}          # left and right Alt, as evdev numbers them
NAMES = {66: "F8", 67: "F9"}


def _event(code, value):
    return SimpleNamespace(code=code, value=value)


def test_evdev_releases_are_passed_on():
    held = set()
    assert wd._evdev_key_action(_event(66, 1), held, MODS, NAMES.get) == ("F8", "press")
    assert wd._evdev_key_action(_event(66, 0), held, MODS, NAMES.get) == ("F8", "release")


def test_evdev_alt_f8_does_not_count_as_f8():
    held = set()
    wd._evdev_key_action(_event(56, 1), held, MODS, NAMES.get)       # Alt down
    assert wd._evdev_key_action(_event(66, 1), held, MODS, NAMES.get) is None
    assert wd._evdev_key_action(_event(66, 0), held, MODS, NAMES.get) is None
    wd._evdev_key_action(_event(56, 0), held, MODS, NAMES.get)       # Alt up
    assert wd._evdev_key_action(_event(66, 0), held, MODS, NAMES.get) == ("F8", "release")


def test_evdev_auto_repeat_and_unknown_keys_are_ignored():
    assert wd._evdev_key_action(_event(66, 2), set(), MODS, NAMES.get) is None
    assert wd._evdev_key_action(_event(30, 1), set(), MODS, NAMES.get) is None

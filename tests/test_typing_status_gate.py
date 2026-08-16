"""Preferences must not hide a half-configured permission state.

The Typing Setup section decides between "configured, just restart" (fix button
disabled) and "not configured" (fix button enabled, so clicking it runs the
usermod/udev setup). That decision must consider BOTH halves of setup:

    udev rule present      -> /dev/uinput write (typing)
    in 'input' group       -> /dev/input read  (hotkeys)

Keying it on the udev rule alone reproduced the Fedora bug this whole changeset
fixes: rule present, user never added to 'input', so the section claimed
"configured - please restart" and DISABLED the only button that would add them.
"""

import types

import pytest


class _FakeLabel:
    def __init__(self):
        self.markup = None

    def set_markup(self, m):
        self.markup = m

    def set_text(self, t):
        self.markup = t


class _FakeButton:
    def __init__(self):
        self.sensitive = None
        self.label = None

    def set_sensitive(self, v):
        self.sensitive = v

    def set_label(self, v):
        self.label = v


def _prefs_with_perms(monkeypatch, *, all_ok, udev, in_group):
    from talktype import prefs as prefs_mod
    from talktype import uinput_helper as uh

    monkeypatch.setattr(uh, "check_all_device_permissions",
                        lambda: (all_ok, "reason"))
    monkeypatch.setattr(uh, "check_udev_rule_exists", lambda: udev)
    monkeypatch.setattr(uh, "check_user_in_input_group", lambda: in_group)

    prefs = prefs_mod.PreferencesWindow.__new__(prefs_mod.PreferencesWindow)
    prefs.typing_status_label = _FakeLabel()
    prefs.fix_typing_button = _FakeButton()
    return prefs


def test_fedora_bug_fix_button_stays_enabled_when_group_missing(monkeypatch):
    # udev rule present, but NOT in the input group, access still failing.
    prefs = _prefs_with_perms(monkeypatch, all_ok=False, udev=True, in_group=False)
    prefs._check_typing_status()
    assert prefs.fix_typing_button.sensitive is True, (
        "must let the user run setup — they were never added to 'input'"
    )
    assert "not configured" in prefs.typing_status_label.markup.lower()


def test_both_configured_but_stale_says_restart_and_disables(monkeypatch):
    # Rule present AND in group (system db), but this session is stale.
    prefs = _prefs_with_perms(monkeypatch, all_ok=False, udev=True, in_group=True)
    prefs._check_typing_status()
    assert prefs.fix_typing_button.sensitive is False
    assert "restart" in prefs.typing_status_label.markup.lower()


def test_full_access_reports_ready(monkeypatch):
    prefs = _prefs_with_perms(monkeypatch, all_ok=True, udev=True, in_group=True)
    prefs._check_typing_status()
    assert prefs.fix_typing_button.sensitive is False
    assert "✓" in prefs.typing_status_label.markup


def test_nothing_configured_enables_fix(monkeypatch):
    prefs = _prefs_with_perms(monkeypatch, all_ok=False, udev=False, in_group=False)
    prefs._check_typing_status()
    assert prefs.fix_typing_button.sensitive is True

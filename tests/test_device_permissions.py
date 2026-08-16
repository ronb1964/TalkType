"""TalkType needs TWO device permissions, granted by two different mechanisms.

Writing keystrokes needs /dev/uinput. Reading hotkeys needs /dev/input/event*.
They are not interchangeable and they are not granted the same way:

    /dev/uinput        crw-rw----+  root input   <- logind sets a per-user ACL
    /dev/input/event*  crw-rw----   root input   <- group membership only

Onboarding used to gate its whole permission-setup step on the uinput check
alone. On Fedora the logind ACL already grants uinput, so that check passed,
setup was skipped, and the `usermod -a -G input` inside it never ran — leaving
the user able to type but unable to read a single hotkey. The dictation service
then started perfectly and ignored every keypress.

On Ubuntu there is no uinput ACL, so the check failed, setup ran, and the group
membership was fixed as a SIDE EFFECT. That accident is why this shipped.
"""

import pytest

from talktype.uinput_helper import (
    check_input_read_permission,
    check_all_device_permissions,
)


def test_reports_failure_when_no_input_device_is_readable(monkeypatch):
    monkeypatch.setattr("talktype.uinput_helper._readable_input_devices", lambda: [])
    ok, reason = check_input_read_permission()

    assert ok is False
    assert "input" in reason.lower()


def test_reports_success_when_a_device_is_readable(monkeypatch):
    monkeypatch.setattr(
        "talktype.uinput_helper._readable_input_devices",
        lambda: ["/dev/input/event3"],
    )
    ok, _ = check_input_read_permission()
    assert ok is True


def test_setup_is_required_when_only_hotkey_reading_is_broken(monkeypatch):
    """The Fedora regression: uinput fine, /dev/input unreadable → MUST still fix.

    This is the exact case the old gate got wrong.
    """
    monkeypatch.setattr(
        "talktype.uinput_helper.check_uinput_permission",
        lambda: (True, "uinput is fine"),
    )
    monkeypatch.setattr("talktype.uinput_helper._readable_input_devices", lambda: [])

    ok, reason = check_all_device_permissions()

    assert ok is False, "setup must run when hotkeys cannot be read"
    assert "input" in reason.lower()


def test_setup_is_required_when_only_typing_is_broken(monkeypatch):
    monkeypatch.setattr(
        "talktype.uinput_helper.check_uinput_permission",
        lambda: (False, "Cannot write to /dev/uinput."),
    )
    monkeypatch.setattr(
        "talktype.uinput_helper._readable_input_devices",
        lambda: ["/dev/input/event3"],
    )

    ok, reason = check_all_device_permissions()

    assert ok is False
    assert "uinput" in reason.lower()


def test_no_setup_needed_when_both_halves_work(monkeypatch):
    monkeypatch.setattr(
        "talktype.uinput_helper.check_uinput_permission",
        lambda: (True, "uinput is fine"),
    )
    monkeypatch.setattr(
        "talktype.uinput_helper._readable_input_devices",
        lambda: ["/dev/input/event3"],
    )

    ok, _ = check_all_device_permissions()
    assert ok is True

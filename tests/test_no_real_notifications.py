"""Running the tests never pops a notification on the developer's desktop.

Tests such as test_a_real_cuda_failure_still_falls_back_to_cpu go through the
real notification path, so conftest holds back Notify.Notification.show for
the whole suite.
"""
import gi

gi.require_version("Notify", "0.7")
from gi.repository import Notify  # noqa: E402

from tuxtalk import app, notify  # noqa: E402


def test_notifications_are_held_back_during_tests():
    assert Notify.Notification.show.__name__ == "_held_back"


def test_app_notify_does_not_reach_the_desktop(monkeypatch):
    assert app._notify is notify.notify
    monkeypatch.setattr(notify, "_ready", True)
    notify.notify("TalkType", "should not appear")    # would pop up without the guard

"""Running the tests never pops a notification on the developer's desktop.

test_a_real_cuda_failure_still_falls_back_to_cpu sent a real "Couldn't use
your NVIDIA graphics card (CUDA)" notification on every suite run, and Ron saw
it pop up through a whole release test without being on CUDA.
"""
import gi

gi.require_version("Notify", "0.7")
from gi.repository import Notify  # noqa: E402

from talktype import app  # noqa: E402


def test_notifications_are_held_back_during_tests():
    assert Notify.Notification.show.__name__ == "_held_back"


def test_app_notify_does_not_reach_the_desktop(monkeypatch):
    monkeypatch.setattr(app, "_notify_ready", True)
    app._notify("TalkType", "should not appear")    # would pop up without the guard

"""evdev's InputDevice has no set_nonblocking(), and doesn't need one.

python-evdev opens every device with O_NONBLOCK already. The calls that were
here raised AttributeError: harmless where they sat in their own try, but in
the welcome screen's hotkey test the error came from inside the loop that
collects keyboards, so every device was skipped and the log said "No
keyboards found via evdev" on every first run (0.14.4 test, 2026-10-10).
"""
import os
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "talktype"


def test_nothing_calls_the_missing_method():
    callers = [f"{p.name}:{n}" for p in SRC.glob("*.py")
               for n, line in enumerate(p.read_text().splitlines(), 1)
               if "set_nonblocking(" in line]
    assert callers == []


def test_evdev_opens_devices_non_blocking():
    """What the removed calls were for. The flush before the hotkey test and
    the service's read loop both rely on it."""
    evdev = pytest.importorskip("evdev")
    paths = evdev.list_devices()
    if not paths:
        pytest.skip("no readable input devices here")
    dev = evdev.InputDevice(paths[0])
    try:
        assert not hasattr(dev, "set_nonblocking")
        assert os.get_blocking(dev.fd) is False
    finally:
        dev.close()

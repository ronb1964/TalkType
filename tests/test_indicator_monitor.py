"""The recording indicator's fixed positions sit on one monitor.

Worked out over the whole screen, which spans every monitor, "center" would
land on the seam between two side-by-side screens, split across both, and
"bottom-*" could land below a shorter monitor.
"""
import pytest

from tuxtalk import recording_indicator as ri
from tuxtalk.window_geometry import Rect

W, H = 200, 180
ONE = Rect(0, 0, 1920, 1080)


def _old_single_screen(position, sw, sh, w, h):
    """The positions the indicator always had on a single monitor."""
    table = {
        "center": ((sw - w) // 2, (sh - h) // 2),
        "top-left": (20, 20),
        "top-center": ((sw - w) // 2, 20),
        "top-right": (sw - w - 20, 20),
        "bottom-left": (20, sh - h - 20),
        "bottom-center": ((sw - w) // 2, sh - h - 20),
        "bottom-right": (sw - w - 20, sh - h - 20),
        "left-center": (20, (sh - h) // 2),
        "right-center": (sw - w - 20, (sh - h) // 2),
        "nonsense": ((sw - w) // 2, (sh - h) // 2),
    }
    return table[position]


@pytest.mark.parametrize("position", ["center", "top-left", "top-center", "top-right",
                                      "bottom-left", "bottom-center", "bottom-right",
                                      "left-center", "right-center", "nonsense"])
def test_one_monitor_keeps_the_positions_it_always_had(position):
    assert ri.fixed_position(position, W, H, ONE) == _old_single_screen(position, 1920, 1080, W, H)


def test_center_is_on_the_chosen_monitor_not_the_seam():
    right = Rect(1920, 0, 1920, 1080)
    x, y = ri.fixed_position("center", W, H, right)
    assert right.x <= x and x + W <= right.x + right.w
    assert (x, y) == (1920 + (1920 - W) // 2, (1080 - H) // 2)


def test_bottom_uses_this_monitors_height():
    """A shorter monitor beside a taller one: bottom must stay on screen."""
    short = Rect(2560, 0, 1920, 1080)
    assert ri.fixed_position("bottom-right", W, H, short) == (2560 + 1920 - W - 20, 1080 - H - 20)


def test_the_offset_is_applied_and_kept_on_the_monitor():
    mon = Rect(1920, 0, 1920, 1080)
    assert ri.fixed_position("top-left", W, H, mon, 30, 40) == (1920 + 50, 60)
    assert ri.fixed_position("top-left", W, H, mon, -5000, -5000) == (1920, 0)
    assert ri.fixed_position("bottom-right", W, H, mon, 5000, 5000) == (3840 - W, 1080 - H)


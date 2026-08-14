"""The recording indicator must accept new settings without being rebuilt.

show_at_position() reads self.position, self.scale and the offsets at show
time rather than at construction, so applying new settings to a running
service is just updating those attributes — the next press of F8 shows the
indicator in the new place. That is what lets Preferences skip the restart.

Also covers a pre-existing sizing bug found while scoping this work:
__init__ called set_default_size(200, 180) unscaled while show_at_position()
computed int(200 * scale) for its positioning maths. At size="large" (1.4x)
the maths assumed a 280x252 window that was really 200x180, putting right- and
bottom-anchored positions roughly 80px away from where they belonged.
"""

import pytest


@pytest.fixture
def indicator():
    """A real RecordingIndicator, skipping when there is no display."""
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    if not Gtk.init_check(None)[0]:
        pytest.skip("no display available")

    from talktype.recording_indicator import RecordingIndicator

    ind = RecordingIndicator(position="center", offset_x=0, offset_y=0, size="medium")
    yield ind
    ind.destroy()
    while Gtk.events_pending():
        Gtk.main_iteration()


class TestApplySettings:
    def test_updates_position_and_offsets(self, indicator):
        indicator.apply_settings("top-left", "medium", 50, -10)

        assert indicator.position == "top-left"
        assert indicator.offset_x == 50
        assert indicator.offset_y == -10

    def test_position_is_normalised_to_lower_case(self, indicator):
        """__init__ lower-cases it; apply_settings must agree or matching fails."""
        indicator.apply_settings("TOP-RIGHT", "medium", 0, 0)
        assert indicator.position == "top-right"

    def test_size_change_updates_scale(self, indicator):
        assert indicator.scale == pytest.approx(1.0)

        indicator.apply_settings("center", "large", 0, 0)
        assert indicator.scale == pytest.approx(1.4)

        indicator.apply_settings("center", "small", 0, 0)
        assert indicator.scale == pytest.approx(0.6)

    def test_unknown_size_falls_back_to_medium(self, indicator):
        """Matches __init__'s behaviour rather than crashing the service loop."""
        indicator.apply_settings("center", "enormous", 0, 0)
        assert indicator.scale == pytest.approx(1.0)


class TestWindowSizeMatchesPositioningMaths:
    """The window must actually be the size the positioning maths assumes."""

    @pytest.mark.parametrize(
        "size,expected_scale", [("small", 0.6), ("medium", 1.0), ("large", 1.4)]
    )
    def test_window_size_tracks_scale_at_construction(self, size, expected_scale):
        gi = pytest.importorskip("gi")
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        if not Gtk.init_check(None)[0]:
            pytest.skip("no display available")

        from talktype.recording_indicator import RecordingIndicator

        ind = RecordingIndicator(size=size)
        try:
            width, height = ind.get_size_request()
            if width <= 0:
                width, height = ind.get_default_size()

            assert width == int(200 * expected_scale), (
                f"Window is {width}px wide but show_at_position() positions it as "
                f"{int(200 * expected_scale)}px. Right- and bottom-anchored "
                f"positions land off by the difference."
            )
            assert height == int(180 * expected_scale)
        finally:
            ind.destroy()

    def test_window_resizes_when_size_changes(self, indicator):
        indicator.apply_settings("center", "large", 0, 0)

        width, height = indicator.get_size_request()
        if width <= 0:
            width, height = indicator.get_default_size()

        assert width == int(200 * 1.4), (
            "apply_settings changed the scale without resizing the window, so "
            "the positioning maths and the real window disagree again."
        )
        assert height == int(180 * 1.4)

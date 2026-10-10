"""Dropdown popups must render as a list below the button, not over it.

By default GTK3 puts a ComboBox popup in "menu mode": it positions the list so
the SELECTED item sits on top of the button, which means the popup covers the
row above and the widget itself. On the Preferences window that reads as a
glitch — the Model row disappears behind the Device popup.

Setting the appears-as-list style property switches it to a normal drop-down
list anchored under the button.

Two things are easy to get wrong here and both are covered below:

1. The property is deprecated (GTK 3.20+). It still resolves in GTK 3.24.52 —
   measured False -> True — but a future GTK could drop it, and this test says
   so plainly rather than leaving a silent cosmetic regression.

2. Scope. prefs.py attaches prefs_style.css to the WINDOW's style context, and
   a window-scoped provider does NOT reach child widgets — measured: the child
   combo still read False. The style must be installed for the whole screen or
   it silently does nothing.

3. Wayland. List mode is X11-only: on Wayland GTK3 can place the list popup off
   screen on a second monitor, so the dropdown can't be changed (issue #9).
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def gtk():
    """Import Gtk, skipping when there is no usable display."""
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        if not Gtk.init_check(None)[0]:
            pytest.skip("no display available")
        return Gtk
    except (ImportError, ValueError) as exc:
        pytest.skip(f"GTK stack unavailable: {exc}")


class _FakeDisplay:
    """Stands in for a GdkDisplay; only the class name matters."""


def _display_named(name):
    return type(name, (_FakeDisplay,), {})()


@pytest.mark.parametrize(
    "class_name, expected",
    [
        ("GdkX11Display", True),
        # Issue #9: on Wayland, GTK3's list-mode popup positions itself with
        # window-relative coordinates clamped against the monitor's GLOBAL work
        # area (gtkcombobox.c gtk_combo_box_list_position). On a monitor that
        # does not start at 0,0 that shoves the popup off screen, so the value
        # can't be changed. Menu mode uses xdg_popup positioning and works.
        ("GdkWaylandDisplay", False),
        ("SomethingElse", False),
    ],
)
def test_list_mode_only_on_x11(class_name, expected):
    from talktype.ui_style import _wants_list_mode

    assert _wants_list_mode(_display_named(class_name)) is expected


def test_list_mode_never_raises_on_odd_input():
    from talktype.ui_style import _wants_list_mode

    assert _wants_list_mode(None) is False


def test_helper_sets_the_right_mode_for_this_display(gtk):
    """A real ComboBox must end up in list mode on X11 and menu mode elsewhere."""
    from gi.repository import Gdk
    from talktype.ui_style import apply_dropdown_list_style, _wants_list_mode

    combo = gtk.ComboBoxText()
    combo.append_text("CPU")
    combo.set_active(0)
    win = gtk.Window()
    win.add(combo)
    win.show_all()
    while gtk.events_pending():
        gtk.main_iteration()

    assert combo.style_get_property("appears-as-list") is False, (
        "Expected GTK's default menu mode before the helper runs. If this fails, "
        "the theme already sets it and this helper may be unnecessary."
    )

    apply_dropdown_list_style()
    while gtk.events_pending():
        gtk.main_iteration()

    expected = _wants_list_mode(Gdk.Display.get_default())
    assert combo.style_get_property("appears-as-list") is expected, (
        "appears-as-list did not match the display backend. On X11 GTK may have "
        "finally dropped this deprecated property (cosmetic only); on Wayland it "
        "must stay off or popups can open off screen (issue #9)."
    )
    win.destroy()


def test_helper_is_idempotent(gtk):
    """The tray calls it once and Preferences calls it again in-process."""
    from talktype.ui_style import apply_dropdown_list_style

    apply_dropdown_list_style()
    apply_dropdown_list_style()  # must not raise or stack providers unboundedly


@pytest.mark.parametrize(
    "module",
    [
        "src/talktype/prefs.py",           # Model, Device, Language, hotkeys
        "src/talktype/welcome_dialog.py",  # first-run model picker
    ],
)
def test_every_window_with_dropdowns_applies_the_style(module):
    """Both live in different processes; neither inherits the other's CSS."""
    text = (ROOT / module).read_text()
    assert "apply_dropdown_list_style" in text, (
        f"{module} builds dropdowns but never calls apply_dropdown_list_style(), "
        f"so its popups will still open in menu mode covering the row above."
    )

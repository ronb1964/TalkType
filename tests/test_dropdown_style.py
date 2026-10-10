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
   Plain menu mode isn't good enough either: on KDE it opens squashed, with
   scroll arrows and half-hidden items, until the mouse moves. So on Wayland
   every combo gets wrap_width=1, GTK's "drop the menu below the button" path,
   which the compositor places, and the menu is made as wide as the button.
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


def _pump(gtk):
    while gtk.events_pending():
        gtk.main_iteration()


def test_drop_down_below_uses_the_wrap_path_and_full_width(gtk):
    """The Wayland treatment for one combo: wrap path, menu as wide as it."""
    from talktype.ui_style import _drop_down_below

    combo = gtk.ComboBoxText()
    for t in ("CPU", "CUDA (GPU)", "Vulkan (any GPU)"):
        combo.append_text(t)
    combo.set_active(2)
    combo.set_size_request(400, -1)
    win = gtk.Window()
    win.add(combo)

    _drop_down_below(combo)
    win.show_all()
    _pump(gtk)

    assert combo.get_wrap_width() == 1
    menu = combo.get_popup_accessible().get_widget()
    # The menu hangs from the button's text, so it's as wide as the button
    # minus that inset: its right edge lines up with the button's.
    inset = combo.get_child().get_allocation().x - combo.get_allocation().x
    assert inset >= 0
    assert menu.get_size_request()[0] == combo.get_allocated_width() - inset
    assert menu.get_size_request()[0] > 300
    win.destroy()


def test_drop_down_below_leaves_an_explicit_wrap_width_alone(gtk):
    from talktype.ui_style import _drop_down_below

    combo = gtk.ComboBoxText()
    combo.set_wrap_width(3)
    _drop_down_below(combo)
    assert combo.get_wrap_width() == 3


def test_helper_gives_combos_the_right_popup_for_this_display(gtk):
    """Combos realised after the helper runs: wrap path on Wayland only."""
    from gi.repository import Gdk
    from talktype.ui_style import apply_dropdown_list_style, _wants_list_mode

    apply_dropdown_list_style()
    combo = gtk.ComboBoxText()
    combo.append_text("F8")
    win = gtk.Window()
    win.add(combo)
    win.show_all()
    _pump(gtk)

    expected = 0 if _wants_list_mode(Gdk.Display.get_default()) else 1
    assert combo.get_wrap_width() == expected
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
        "src/talktype/fix_word_dialog.py", # which recent dictation
    ],
)
def test_every_window_with_dropdowns_applies_the_style(module):
    """Both live in different processes; neither inherits the other's CSS."""
    text = (ROOT / module).read_text()
    assert "apply_dropdown_list_style" in text, (
        f"{module} builds dropdowns but never calls apply_dropdown_list_style(), "
        f"so its popups will still open in menu mode covering the row above."
    )

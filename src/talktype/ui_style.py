"""Shared GTK styling that must be installed screen-wide.

Kept in one place because TalkType draws dropdowns from two different processes
— the tray (welcome dialog) and Preferences — and neither inherits the other's
CSS. Duplicating the rule invites fixing it in one and forgetting the other.
"""

import logging

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GObject

logger = logging.getLogger(__name__)

# GTK3 defaults ComboBox popups to "menu mode", which positions the list so the
# selected item sits on top of the button. On the Preferences window that means
# the Device popup opens over the Model row and hides it, which reads as a
# rendering glitch. List mode anchors the popup under the button instead.
#
# appears-as-list is a style property, deprecated since GTK 3.20 but still
# honoured in 3.24.52 (verified: the resolved value flips False -> True). If a
# future GTK drops it the popups revert to menu mode — cosmetic only, nothing
# stops working.
#
# X11 ONLY (issue #9). On Wayland a window can't learn its place on the desktop,
# so GTK3 (gtkcombobox.c, gtk_combo_box_list_position) gets the list's position
# relative to the window and then clamps it against the monitor's work area in
# GLOBAL coordinates. On a monitor that doesn't start at 0,0 (a second screen)
# that shoves the popup off screen and the value can't be changed. GTK bug #6105,
# open and unfixed. Wayland gets _drop_down_below() instead, see there.
_DROPDOWN_CSS = b"""
combobox {
    -GtkComboBox-appears-as-list: 1;
}
"""

# The color picker's preset swatches draw a checkmark on the SELECTED color.
# The theme's default left that checkmark white, so on the white swatch it was
# invisible — you couldn't tell white was selected. GTK already tags each swatch
# .light or .dark by its own luminance, so key off that: a near-black check on
# light swatches (white, amber…) and a near-white check on dark ones (black,
# purple…). The checkmark is a symbolic icon that follows the node's `color`, so
# setting `color` on the swatch and its overlay child recolors just the check.
_SWATCH_CSS = b"""
colorswatch.light,
colorswatch.light overlay {
    color: #141414;
}
colorswatch.dark,
colorswatch.dark overlay {
    color: #f5f5f5;
}
"""

# Style properties resolve from the widget's own context, and a provider added
# to a window's context does NOT reach that window's children (verified: a child
# combo still read False). It has to go on the screen, so guard against stacking
# a fresh provider every time a dialog opens.
_installed = False


def _wants_list_mode(display):
    """True only on X11, the one backend where GTK3 places list popups correctly.

    Checked by class name so it needs no GdkX11 typelib. Anything unrecognised
    gets GTK's default menu mode, which is safe everywhere. Never raises.
    """
    try:
        return type(display).__name__.startswith("GdkX11")
    except Exception:
        return False


def _match_menu_width(combo, allocation):
    """Keep a wrap-mode combo's popup menu as wide as the combo itself.

    GTK only sizes the menu to the button in plain menu mode; in wrap mode it is
    as narrow as its longest item, which looks detached from a wide button. The
    menu hangs from the button's text, not its edge (measured on KDE: 17 px in),
    so take that inset off or the menu overhangs the button's right side.
    """
    try:
        acc = combo.get_popup_accessible()
        menu = acc.get_widget() if acc is not None else None
        if menu is None:
            return
        width = allocation.width
        child = combo.get_child()
        if child is not None:
            inset = child.get_allocation().x - allocation.x
            if 0 < inset < width:
                width -= inset
        if menu.get_size_request()[0] != width:
            menu.set_size_request(width, -1)
    except Exception as e:
        logger.debug(f"_match_menu_width failed: {e}")


def _drop_down_below(combo):
    """Make one combo's popup drop down below the button, the Wayland way.

    Plain menu mode lines the selected item up over the button and corrects its
    scroll position after the compositor has placed it (gtkcombobox.c,
    gtk_menu_update_scroll_offset). On KDE that leaves the first open squashed,
    with scroll arrows and half-hidden items, until the mouse moves. With a wrap
    width GTK takes its other path instead: the menu hangs below the button and
    the compositor places it (flip, slide or resize), so it's correct on any
    monitor too. One column looks the same as a normal list.

    Leaves a combo that already has a wrap width alone. Never raises.
    """
    try:
        if combo.get_wrap_width() == 0:
            combo.set_wrap_width(1)
            combo.connect("size-allocate", _match_menu_width)
    except Exception as e:
        logger.debug(f"_drop_down_below failed: {e}")


def _on_widget_realize(widget, *_args):
    """Emission hook: give every ComboBox the Wayland drop-down treatment as it
    is realised, before anyone can click it. Returns True to stay installed."""
    if isinstance(widget, Gtk.ComboBox):
        _drop_down_below(widget)
    return True


def apply_dropdown_list_style():
    """Install shared screen-wide GTK styling: ComboBox popups drop down below
    the button (not over it), through list mode on X11 and the wrap path on
    Wayland; and color-picker swatch checkmarks contrast with the swatch color
    so the selection is visible on white and black alike.

    Safe to call more than once; only the first call installs anything. Never
    raises — a styling failure must not stop a window from opening.
    """
    global _installed
    if _installed:
        return

    screen = Gdk.Screen.get_default()
    if screen is None:
        # No display (headless run). Nothing to style.
        return

    try:
        provider = Gtk.CssProvider()
        list_mode = _wants_list_mode(screen.get_display())
        css = _DROPDOWN_CSS + _SWATCH_CSS if list_mode else _SWATCH_CSS
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        if not list_mode:
            # One hook for the whole process catches every combo, including
            # ones built later, so no window has to remember to opt in.
            GObject.add_emission_hook(Gtk.Widget, "realize", _on_widget_realize)
        _installed = True
    except Exception as e:
        logger.warning(f"Could not apply dropdown list style: {e}")


def forward_combo_scroll(combo):
    """Make scrolling over a ComboBox scroll the *page*, not change the combo.

    GTK ComboBoxes eat scroll events to cycle their selection. The old fix just
    returned True to swallow the event — which stopped the value from changing
    but also left the surrounding ScrolledWindow stuck whenever the pointer sat
    over a dropdown (you had to move the mouse off the combo to scroll at all).

    Instead, forward the scroll to the nearest ScrolledWindow ancestor so the
    page scrolls under the cursor, and still return True so the combo's own
    value never changes. Never raises — a scroll-handler failure must not break
    the dialog.
    """
    def _on_scroll(widget, event):
        try:
            sw = widget.get_ancestor(Gtk.ScrolledWindow)
            adj = sw.get_vadjustment() if sw is not None else None
            if adj is not None:
                step = adj.get_step_increment()
                if not step or step <= 0:
                    step = 40.0
                direction = event.direction
                if direction == Gdk.ScrollDirection.UP:
                    adj.set_value(adj.get_value() - step)
                elif direction == Gdk.ScrollDirection.DOWN:
                    adj.set_value(adj.get_value() + step)
                elif direction == Gdk.ScrollDirection.SMOOTH:
                    ok, _dx, dy = event.get_scroll_deltas()
                    if ok:
                        adj.set_value(adj.get_value() + dy * step)
        except Exception as e:
            logger.debug(f"forward_combo_scroll failed: {e}")
        return True  # never let the combo change its value on scroll

    combo.connect("scroll-event", _on_scroll)


def fit_dialog_to_screen(dialog, width, desired_height, min_height=320, margin=96):
    """Size a dialog to (width, desired_height) but never taller than the monitor's
    work area, and always make it resizable.

    First-run / onboarding dialogs are tall. On a screen shorter than the dialog — a
    1080p VM, a laptop, a scaled/HiDPI display — a fixed height with resizable=False
    runs the footer buttons off the bottom edge with no way to reach them: GNOME on
    Wayland won't reliably let the user move, resize, or maximize such a window, so
    they get stuck (this is exactly what happened on the Ubuntu 26.04 VM test).
    Capping the height to the work area guarantees the whole window — action buttons
    included — stays on-screen, and resizable=True lets the user fine-tune it.

    Pass desired_height < 0 to keep GTK's content-based auto-height (still resizable).
    For content that can exceed the cap, wrap it in a Gtk.ScrolledWindow so the
    overflow scrolls instead of being clipped.

    Never raises — a sizing failure must not stop a window from opening.
    """
    try:
        dialog.set_resizable(True)
        if desired_height is None or desired_height < 0:
            dialog.set_default_size(width, -1)
            return dialog

        avail = None
        display = Gdk.Display.get_default()
        if display is not None:
            monitor = display.get_primary_monitor()
            if monitor is None and display.get_n_monitors() > 0:
                monitor = display.get_monitor(0)
            if monitor is not None:
                avail = monitor.get_workarea().height
        if avail is not None:
            desired_height = min(desired_height, max(min_height, avail - margin))
        dialog.set_default_size(width, desired_height)
    except Exception as e:
        logger.warning(f"fit_dialog_to_screen failed: {e}")
        try:
            dialog.set_default_size(width, desired_height if (desired_height or 0) > 0 else -1)
        except Exception:
            pass
    return dialog

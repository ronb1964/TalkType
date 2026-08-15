"""Shared GTK styling that must be installed screen-wide.

Kept in one place because TalkType draws dropdowns from two different processes
— the tray (welcome dialog) and Preferences — and neither inherits the other's
CSS. Duplicating the rule invites fixing it in one and forgetting the other.
"""

import logging

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk

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
_DROPDOWN_CSS = b"""
combobox {
    -GtkComboBox-appears-as-list: 1;
}
"""

# Style properties resolve from the widget's own context, and a provider added
# to a window's context does NOT reach that window's children (verified: a child
# combo still read False). It has to go on the screen, so guard against stacking
# a fresh provider every time a dialog opens.
_installed = False


def apply_dropdown_list_style():
    """Make ComboBox popups drop down below the button instead of over it.

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
        provider.load_from_data(_DROPDOWN_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        _installed = True
    except Exception as e:
        logger.warning(f"Could not apply dropdown list style: {e}")


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

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

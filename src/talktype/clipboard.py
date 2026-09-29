"""
Put text on the clipboard from TalkType's own windows and menus.

Shared by the tray's Recent Dictations (Copy) and the Fix a Word window,
which can be opened from the tray or from Preferences.
"""
import os
import shutil
import subprocess

from .logger import setup_logger

logger = setup_logger(__name__)


def copy_text(text):
    """Copy *text*; returns True on success. Never raises.

    wl-copy first: a click in a KDE/GNOME tray menu is handled by the
    desktop's menu, not a GTK window of ours, and Wayland only lets a
    focused window set the clipboard through GTK. wl-copy has its own way
    in. GTK's clipboard covers X11.
    """
    try:
        if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
            subprocess.run(["wl-copy"], input=text.encode("utf-8"), timeout=5, check=True)
        else:
            import gi
            gi.require_version('Gtk', '3.0')
            from gi.repository import Gtk, Gdk
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(text, -1)
            clipboard.store()
        return True
    except Exception as e:
        logger.error(f"Could not copy to the clipboard: {e}")
        return False

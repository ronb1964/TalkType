"""Tell the desktop which launcher TalkType's windows belong to.

The desktop finds a window's icon (title bar, taskbar, Alt+Tab) by matching
the program name, which becomes the Wayland app_id or the X11 WM_CLASS, to a
launcher (.desktop file). Without it every TalkType window reported itself as
"python3", and KDE showed its generic "W" icon instead of TalkType's.

Each install type names its launcher differently, so the name follows the
install:

  AppImage   ~/.local/share/applications/talktype.desktop  (made at first run)
  AUR        /usr/share/applications/talktype.desktop
  deb / rpm  /usr/share/applications/io.github.ronb1964.TalkType.desktop
  Flatpak    io.github.ronb1964.TalkType
  dev        ~/.local/share/applications/talktype-dev.desktop

Call apply() at the start of every process that opens windows (the tray,
Preferences and the dictation service). It works even after Gtk has been
imported, as long as it runs before the first window is shown.
"""
from gi.repository import GLib

APP_ID = "io.github.ronb1964.TalkType"

_BY_INSTALL_TYPE = {
    "appimage": "talktype",
    "aur": "talktype",
    "dev": "talktype-dev",
}


def desktop_id(install_type: str) -> str:
    """The launcher name (without .desktop) for this kind of install."""
    return _BY_INSTALL_TYPE.get(install_type, APP_ID)


def apply() -> None:
    """Set the program name to this install's launcher name. Never raises:
    a missing icon is cosmetic, a crash at startup is not."""
    try:
        from .update_checker import get_install_type
        GLib.set_prgname(desktop_id(get_install_type()))
    except Exception:
        pass

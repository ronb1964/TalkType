"""Where the active window is, in the coordinates TuxTalk's own windows use.

Wayland doesn't let an app ask where other apps' windows are, so this asks
whoever does know, first answer wins:
  1. the tray's cache, which KDE's KWin script (kwin_focus.py) and the GNOME
     extension push to, the way they already push the window's class;
  2. Sway / i3 and Hyprland directly (compositor_focus.focused_rect);
  3. in an X11 session, the window manager, through GDK.
Nothing answered: None, and the caller uses the middle of the screen.

The answer is in the compositor's logical coordinates. TuxTalk's windows (the
recording indicator, screen_message) are drawn through X11 / XWayland, which
on a scaled screen counts physical pixels, so to_screen_point() maps the
point into GDK's monitor of the same name.
Spec: docs/superpowers/specs/2026-10-12-messages-at-active-window-design.md
"""
import os
from collections import namedtuple

from .logger import setup_logger

logger = setup_logger(__name__)

Rect = namedtuple("Rect", "x y w h")

_DBUS_TIMEOUT_S = 0.3     # the tray answers from a cache in a millisecond


def _rect(text):
    parts = [int(round(float(p))) for p in text.split(",")]
    if len(parts) != 4:
        raise ValueError(text)
    return Rect(*parts)


def parse_reported(text):
    """("x,y,w,h|output|ox,oy,ow,oh") -> (window Rect, output name, output Rect),
    or None when there is no usable report."""
    try:
        window, output, output_rect = text.split("|")
        return _rect(window), output, _rect(output_rect)
    except (ValueError, AttributeError):
        return None


def to_screen_point(rect, output, output_rect, monitors):
    """The middle of *rect* (compositor coordinates) where GDK draws it.

    *monitors* is [(name, Rect)] as GDK sees them. The point keeps its offset
    within its monitor, scaled from the compositor's size of that monitor to
    GDK's. Without a matching name a single monitor is still used; with
    several, or no monitor size at all, coordinates are taken as they are."""
    cx, cy = rect.x + rect.w / 2, rect.y + rect.h / 2
    if output_rect is None or output_rect.w <= 0 or output_rect.h <= 0:
        return round(cx), round(cy)
    match = [m for name, m in monitors if output and name == output]
    if not match and len(monitors) == 1:
        match = [monitors[0][1]]
    if not match:
        return round(cx), round(cy)
    mon = match[0]
    sx, sy = mon.w / output_rect.w, mon.h / output_rect.h
    return round(mon.x + (cx - output_rect.x) * sx), round(mon.y + (cy - output_rect.y) * sy)


def screen_monitors():
    """[(name, Rect)] for each monitor as GDK sees it. The name is the
    connector ("DP-6") where GDK knows it."""
    try:
        import gi
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk
        display = Gdk.Display.get_default()
        out = []
        for i in range(display.get_n_monitors()):
            mon = display.get_monitor(i)
            g = mon.get_geometry()
            out.append((mon.get_model() or "", Rect(g.x, g.y, g.width, g.height)))
        return out
    except Exception as e:
        logger.debug(f"Could not list the monitors: {e}")
        return []


def _reported():
    """What the KWin script or GNOME extension last told the tray, or None."""
    try:
        import dbus
        from .dbus_service import DBUS_INTERFACE, DBUS_NAME, DBUS_PATH
        proxy = dbus.SessionBus().get_object(DBUS_NAME, DBUS_PATH, introspect=False)
        return str(proxy.GetFocusedWindowGeometry(dbus_interface=DBUS_INTERFACE,
                                                  timeout=_DBUS_TIMEOUT_S)) or None
    except Exception as e:
        logger.debug(f"Could not ask the tray where the active window is: {e}")
        return None


def _x11_active_rect():
    """The active window's frame in an X11 session, from the window manager.
    Not under Wayland: XWayland knows only the X11 apps."""
    if os.environ.get("XDG_SESSION_TYPE") != "x11":
        return None
    try:
        import gi
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk
        window = Gdk.Screen.get_default().get_active_window()
        if window is None:
            return None
        g = window.get_frame_extents()
        return Rect(g.x, g.y, g.width, g.height)
    except Exception as e:
        logger.debug(f"Could not ask X11 where the active window is: {e}")
        return None


def active_window_center():
    """The middle of the active window where TuxTalk's own windows are drawn,
    or None when nothing could say."""
    from . import compositor_focus
    monitors = screen_monitors()
    reported = _reported()
    parsed = parse_reported(reported) if reported else None
    if parsed:
        return to_screen_point(*parsed, monitors)
    rect = compositor_focus.focused_rect()
    if rect:
        return to_screen_point(rect, "", None, monitors)
    rect = _x11_active_rect()
    if rect:
        return to_screen_point(rect, "", None, monitors)
    return None

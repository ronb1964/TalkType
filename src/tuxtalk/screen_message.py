"""A short message floating where the user is looking: over the middle of
the active window (window_geometry), for a few seconds, then gone.

The corner notification is easy to miss on a big screen (Ron, 2026-10-12).
This is a pill-shaped label, not a window: it takes no focus, clicks go
through it, and there is nothing to close. The caller still sends the usual
notification as a backup, which stays in the notification history.

Drawn in the dictation service, which runs GTK on X11 / XWayland (for the
recording indicator), as an override-redirect popup, so it goes exactly
where it is put on every desktop.
Spec: docs/superpowers/specs/2026-10-12-messages-at-active-window-design.md
"""
from .logger import setup_logger

logger = setup_logger(__name__)

# On screen long enough to read: a few seconds plus a little per word, so a
# short label stays 4 s and a longer one up to 8 (Ron, 2026-10-12: 3 s faded
# before he had read it). Keep the text short all the same: it's glanced at.
MIN_SECONDS, MAX_SECONDS, SECONDS_PER_WORD = 4.0, 8.0, 0.4
_PAD_X, _PAD_Y = 18, 10
_current = None          # the label on screen, replaced by the next one


def reading_seconds(text):
    """How long *text* stays on screen."""
    seconds = 2.0 + SECONDS_PER_WORD * len(text.split())
    return round(min(MAX_SECONDS, max(MIN_SECONDS, seconds)), 1)


def place(width, height, center, monitor):
    """Top-left corner for a *width* x *height* label centred on *center*,
    kept inside *monitor* (a window_geometry.Rect)."""
    x = round(center[0] - width / 2)
    y = round(center[1] - height / 2)
    x = max(monitor.x, min(x, monitor.x + monitor.w - width))
    y = max(monitor.y, min(y, monitor.y + monitor.h - height))
    return x, y


def show(text, center=None):
    """Show *text* centred on *center* (None: the middle of the main screen).
    Safe from any thread; never raises."""
    try:
        from gi.repository import GLib
        GLib.idle_add(_show_now, text, center)
    except Exception as e:
        logger.debug(f"Could not show the message: {e}")


def _show_now(text, center):
    global _current
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import Gdk, GLib, Gtk, PangoCairo
        import cairo
        from .window_geometry import Rect

        display = Gdk.Display.get_default()
        if center is None:
            mon = display.get_primary_monitor() or display.get_monitor(0)
            g = mon.get_geometry()
            center = (g.x + g.width // 2, g.y + g.height // 2)
        g = (display.get_monitor_at_point(*center) or display.get_monitor(0)).get_geometry()
        monitor = Rect(g.x, g.y, g.width, g.height)

        win = Gtk.Window(type=Gtk.WindowType.POPUP)
        win.set_app_paintable(True)
        visual = win.get_screen().get_rgba_visual()
        if visual is not None:
            win.set_visual(visual)
        win.set_accept_focus(False)
        win.set_keep_above(True)

        layout = win.create_pango_layout("")
        layout.set_markup(f'<span size="large">⚠  {GLib.markup_escape_text(text)}</span>', -1)
        text_w, text_h = layout.get_pixel_size()
        width, height = text_w + 2 * _PAD_X, text_h + 2 * _PAD_Y
        win.set_default_size(width, height)
        win.move(*place(width, height, center, monitor))

        def draw(_widget, cr):
            cr.set_operator(cairo.OPERATOR_SOURCE)
            cr.set_source_rgba(0, 0, 0, 0)
            cr.paint()
            cr.set_operator(cairo.OPERATOR_OVER)
            r = height / 2
            cr.new_sub_path()
            cr.arc(width - r, r, r, -1.5708, 1.5708)
            cr.arc(r, r, r, 1.5708, 4.7124)
            cr.close_path()
            cr.set_source_rgba(0.12, 0.12, 0.13, 0.94)
            cr.fill_preserve()
            cr.set_source_rgba(0.94, 0.62, 0.15, 1.0)     # amber edge: a warning
            cr.set_line_width(1.5)
            cr.stroke()
            cr.move_to(_PAD_X, _PAD_Y)
            cr.set_source_rgba(0.98, 0.93, 0.85, 1.0)
            PangoCairo.show_layout(cr, layout)
            return True

        win.connect("draw", draw)
        # Clicks go through to whatever is underneath.
        win.connect("realize", lambda w: w.input_shape_combine_region(cairo.Region()))
        if _current is not None:
            _current.destroy()
        _current = win
        win.show_all()

        def done():
            global _current
            if _current is win:
                _current = None
            win.destroy()
            return False
        GLib.timeout_add(int(reading_seconds(text) * 1000), done)
    except Exception as e:
        logger.warning(f"Could not show the message on screen: {e}")
    return False

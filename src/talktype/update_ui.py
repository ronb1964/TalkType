"""Shared GTK flow for updating a package (.rpm/.deb) install.

Downloads the correct package for the current install type, installs it as root
via pkexec (the desktop shows a PolicyKit password prompt so it goes through the
system package manager — dependencies resolved, package DB kept correct), then
offers to restart. Used by both the tray "Check for Updates" dialog and the
Preferences → Updates tab so the behaviour stays identical.
"""
import logging
import threading

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # noqa: E402

from . import update_checker  # noqa: E402

logger = logging.getLogger(__name__)


def _set_margins(widget, value):
    widget.set_margin_start(value)
    widget.set_margin_end(value)
    widget.set_margin_top(value)
    widget.set_margin_bottom(value)


def run_package_update(release, install_type):
    """Download + pkexec-install the .rpm/.deb for `install_type`, then offer to
    restart. Shows its own progress and result dialogs. Call from the GTK thread."""
    url, filename = update_checker.get_package_asset(release, install_type)
    if not url:
        _error("This release has no package for your install type.\n"
               "Please update from the GitHub release page.")
        return

    progress = Gtk.Dialog(title="Updating TalkType", flags=Gtk.DialogFlags.MODAL)
    progress.set_default_size(440, 130)
    progress.set_position(Gtk.WindowPosition.CENTER)
    progress.set_keep_above(True)
    content = progress.get_content_area()
    content.set_spacing(10)
    _set_margins(content, 20)
    status = Gtk.Label(label="Starting download…")
    status.set_halign(Gtk.Align.START)
    content.pack_start(status, False, False, 0)
    bar = Gtk.ProgressBar()
    bar.set_show_text(True)
    content.pack_start(bar, False, False, 10)
    progress.show_all()

    def progress_cb(message, percent):
        GLib.idle_add(lambda: status.set_text(message))
        GLib.idle_add(lambda: bar.set_fraction(percent / 100.0))
        GLib.idle_add(lambda: bar.set_text(f"{percent}%"))

    def finish(success, message):
        progress.destroy()
        if success:
            _installed_restart_prompt()
        else:
            _error(message)

    def worker():
        path = update_checker.download_update(
            url, filename, progress_cb,
            checksums_url=release.get("checksums_url"))
        if not path:
            GLib.idle_add(lambda: finish(
                False, "The download could not be completed. "
                "Please try again or update from GitHub."))
            return
        GLib.idle_add(lambda: status.set_text(
            "Waiting for your password to install…"))
        ok, msg = update_checker.install_package_update(path, install_type)
        GLib.idle_add(lambda: finish(ok, msg))

    threading.Thread(target=worker, daemon=True).start()


def _installed_restart_prompt():
    done = Gtk.Dialog(title="Update Installed", flags=Gtk.DialogFlags.MODAL)
    done.set_position(Gtk.WindowPosition.CENTER)
    done.set_keep_above(True)
    dc = done.get_content_area()
    _set_margins(dc, 20)
    lbl = Gtk.Label()
    lbl.set_markup("<b>Update installed!</b>\n"
                   "Restart TalkType to use the new version.")
    lbl.set_halign(Gtk.Align.START)
    lbl.set_line_wrap(True)
    dc.pack_start(lbl, False, False, 0)
    done.add_button("Later", Gtk.ResponseType.CLOSE)
    rb = done.add_button("Restart Now", Gtk.ResponseType.OK)
    rb.get_style_context().add_class("suggested-action")

    def _resp(d, r):
        d.destroy()
        if r == Gtk.ResponseType.OK:
            ok, msg = update_checker.restart_via_launcher()
            if not ok:  # execv normally never returns on success
                logger.error(f"Auto-restart failed: {msg}")
    done.connect("response", _resp)
    done.show_all()
    done.present()


def _error(message):
    err = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR,
                            buttons=Gtk.ButtonsType.OK, text="Update Failed")
    err.format_secondary_text(message)
    err.set_position(Gtk.WindowPosition.CENTER)
    err.set_keep_above(True)
    err.connect("response", lambda d, _r: d.destroy())
    err.show_all()
    err.present()

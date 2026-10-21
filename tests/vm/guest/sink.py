#!/usr/bin/python3
"""A plain text window for TuxTalk to type into during the VM release tests.

Every change to its text is written straight to a file, so the harness can
read exactly what was typed, Enter presses included, without screenshots.
SIGUSR1 empties it between checks (its pid is in OUTPUT_FILE.pid). Runs
with the guest's own python3 and GTK 3. With "password" it is one password
box instead, which TuxTalk must leave empty.

Usage: sink.py OUTPUT_FILE [TITLE] [password]
"""
import os
import signal
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402


def main():
    out_path = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else "TT Sink"
    password = sys.argv[3:] == ["password"]
    # Its own app id per file: TuxTalk tells windows apart by app, so two
    # test windows must look like two apps for a window switch to count.
    GLib.set_prgname("tt-" + os.path.splitext(os.path.basename(out_path))[0])

    window = Gtk.Window(title=title)
    window.set_default_size(1000, 700)
    if password:
        # Filling the window, so the harness's click in the middle lands in it.
        view = Gtk.Entry(visibility=False)
        window.add(view)
        changes, text = view, view.get_text
    else:
        view = Gtk.TextView()
        view.set_wrap_mode(Gtk.WrapMode.WORD)
        scroller = Gtk.ScrolledWindow()
        scroller.add(view)
        window.add(scroller)
        changes = view.get_buffer()
        text = lambda: changes.get_text(*changes.get_bounds(), True)  # noqa: E731

    def save(*_):
        tmp = out_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text())
        os.replace(tmp, out_path)

    def clear():
        changes.set_text("")
        return GLib.SOURCE_CONTINUE

    with open(out_path + ".pid", "w") as f:
        f.write(str(os.getpid()))
    changes.connect("changed", save)
    save()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, clear)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    window.maximize()
    view.grab_focus()
    Gtk.main()


if __name__ == "__main__":
    main()

"""
Bring one of TalkType's already-open windows to the front.

Plain Gtk.Window.present() is not enough on Wayland: a window may only take
focus with an activation token from recent user input, and a tray-menu click
is input to the desktop's panel, not to us. KWin then leaves the window where
it is (maybe flashing it in the taskbar), so a second "open" looked like it
did nothing. Unmapping and remapping makes it a newly shown window, which the
compositor places in front like any window that just opened. The widgets
(current tab, unsaved edits) are untouched; only the on-screen surface is
recreated.
"""


def raise_window(window):
    if window.get_visible():
        window.hide()
    window.show()
    window.present()

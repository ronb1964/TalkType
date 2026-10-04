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


def copy_text_on_gtk_thread(text, timeout=1.0):
    """copy_text, run on the thread that runs Gtk.main(). True on success.

    For the dictation service on X11, which has no wl-copy to lean on. GTK may
    only be touched from its own thread, and the service's typing runs on
    another one, so the copy is queued there and waited for. The service keeps
    the X11 clipboard selection afterwards and its GTK loop answers the
    target app's paste request. If the loop isn't running, nothing happens
    within *timeout* and this returns False.
    """
    import threading
    from gi.repository import GLib

    done = threading.Event()
    result = []

    def _copy():
        result.append(copy_text(text))
        done.set()
        return False            # run once

    GLib.idle_add(_copy)
    return done.wait(timeout) and bool(result and result[0])


# --- Paste mode and the user's clipboard (GitHub issue #7) ----------------------------
# Paste mode puts each dictation on the clipboard and sends Ctrl+V. That used to
# throw away whatever the user had copied, and KDE's Klipper saved every
# dictation into its history on disk. Dictations are now always offered with
# wl-copy --sensitive, the x-kde-passwordManagerHint=secret marker KeePassXC
# uses, which Klipper and other clipboard managers skip. With the
# restore_clipboard setting on, ClipboardKeeper also puts the old contents back
# once the app has had time to read the paste. It's off by default: some people
# (Ron among them) re-paste a dictation that landed in the wrong window.

import functools
import threading

RESTORE_DELAY_S = 0.5           # apps read the clipboard asynchronously after Ctrl+V
_MAX_SAVED_BYTES = 20 * 1024 * 1024
_TEXT_TYPES = ("text/plain;charset=utf-8", "text/plain", "UTF8_STRING", "STRING", "TEXT")
_NOTHING = object()             # nothing saved (setting off, or the clipboard couldn't be read)
_EMPTY = object()               # the clipboard was empty before the paste


def _wl_copy_help():
    result = subprocess.run(["wl-copy", "--help"], capture_output=True, text=True, timeout=3)
    return result.stdout + result.stderr


@functools.lru_cache(maxsize=1)
def _sensitive_supported():
    """wl-copy --sensitive arrived in wl-clipboard 2.3.0 (some distros back-port it)."""
    try:
        return "--sensitive" in _wl_copy_help()
    except Exception:
        return False


def wl_copy_command():
    """The wl-copy command for putting a dictation on the clipboard."""
    return ["wl-copy", "--sensitive"] if _sensitive_supported() else ["wl-copy"]


def _wl_paste_types():
    result = subprocess.run(["wl-paste", "--list-types"], capture_output=True, text=True, timeout=1)
    return [t for t in result.stdout.splitlines() if t.strip()] if result.returncode == 0 else []


def _wl_paste(mime):
    result = subprocess.run(["wl-paste", "--no-newline", "--type", mime], capture_output=True, timeout=1)
    if result.returncode != 0:
        raise OSError(f"wl-paste exited {result.returncode}")
    return result.stdout


def _wl_copy_bytes(data, mime):
    subprocess.run(["wl-copy", "--type", mime], input=data, timeout=3, check=True)


def _wl_clear():
    subprocess.run(["wl-copy", "--clear"], timeout=3, check=True)


def _best_type(types):
    """The type to save: plain text if offered, otherwise the first one (an image, say)."""
    for wanted in _TEXT_TYPES:
        if wanted in types:
            return wanted
    return types[0] if types else None


def _timer(delay, fn):
    t = threading.Timer(delay, fn)
    t.daemon = True
    t.start()
    return t.cancel


class ClipboardKeeper:
    """Puts the user's clipboard back after a paste.

    before_paste() saves it; after_paste(text) restores it RESTORE_DELAY_S
    later, but only if the clipboard still holds the dictation, so something
    the user copied in the meantime is left alone. A second paste before the
    restore keeps the original saved copy, so the user gets back what they
    copied, not the first dictation. Never raises: a clipboard that can't be
    read is simply not restored."""

    def __init__(self, schedule=_timer, delay=RESTORE_DELAY_S):
        self._schedule, self._delay = schedule, delay
        self._lock = threading.Lock()
        self._saved = _NOTHING
        self._cancel = None
        self._generation = 0

    def _read(self):
        try:
            types = _wl_paste_types()
            if not types:
                return _EMPTY
            mime = _best_type(types)
            data = _wl_paste(mime)
            if len(data) > _MAX_SAVED_BYTES:
                logger.info("Clipboard contents too large to keep; not restoring them")
                return _NOTHING
            return data, mime
        except Exception as e:
            logger.info(f"Couldn't read the clipboard to restore it later: {e}")
            return _NOTHING

    def before_paste(self):
        with self._lock:
            self._generation += 1
            if self._cancel is not None:
                # A restore is still pending, so the clipboard holds the last
                # dictation; the copy saved before that one is the user's.
                self._cancel()
                self._cancel = None
                return
            self._saved = self._read()

    def after_paste(self, text):
        with self._lock:
            if self._saved is _NOTHING:
                return
            generation = self._generation
            self._cancel = self._schedule(self._delay, lambda: self._restore(text, generation))

    def _restore(self, text, generation):
        with self._lock:
            if generation != self._generation:
                return          # a newer paste took over; it will restore
            saved, self._saved, self._cancel = self._saved, _NOTHING, None
        if saved is _NOTHING:
            return
        try:
            current = _wl_paste(_best_type(_wl_paste_types()) or "text/plain")
        except Exception:
            current = None
        if current != text.encode("utf-8"):
            logger.info("Clipboard changed after the paste; leaving it as it is")
            return
        try:
            if saved is _EMPTY:
                _wl_clear()
            else:
                _wl_copy_bytes(*saved)
            logger.info("Clipboard restored after paste")
        except Exception as e:
            logger.warning(f"Couldn't restore the clipboard: {e}")

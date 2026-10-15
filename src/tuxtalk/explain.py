"""A small window that explains how a feature works, for the problems that
are really "here's the rule" rather than errors: "select that" said in the
wrong place, voice editing in a terminal, bold in a plain-text app.

The floating label is glanced at, and the notification is gone in seconds,
too quickly to read a whole explanation. So the first time one of these
comes up in a TuxTalk run, this window opens over the app and stays until
"Got it". After that the short floating label is enough, and ticking "Don't
explain this again" leaves it at the label for good (explained.json, next
to the settings).

It runs as its own process, like Preferences: the dictation service draws
on XWayland (for the recording indicator), and a real window with a
button belongs on the desktop's own Wayland.
"""
import json
import os
import subprocess
import sys

from .logger import setup_logger

logger = setup_logger(__name__)

# kind -> (title, explanation). The kinds are app._EDIT_NOTICES'.
EXPLANATIONS = {
    "nothing_said": (
        "Select works right after you dictate",
        "“Select that” and “select the last sentence” work on what you "
        "just said, right after you dictate it. TuxTalk can't see what's in your "
        "document otherwise.\n\n"
        "For other text, say “select the previous 3 words” or “select the "
        "line”, or use the mouse."),
    "undo_other_window": (
        "Delete works right after you dictate",
        "“Delete last word” and “delete last sentence” remove what you "
        "just said, right after you dictate it. TuxTalk can't see what's in your "
        "document otherwise, so it didn't delete anything here.\n\n"
        "To undo something else, press Ctrl+Z in the app."),
    "nav_terminal": (
        "Select and move don't work in a terminal",
        "In a terminal, keys like Ctrl+A and Shift+arrows do other things (Ctrl+A "
        "jumps to the start of the line), so TuxTalk doesn't press them there.\n\n"
        "Use select and move in text editors, word processors, browsers and chat boxes."),
    "terminal": (
        "Voice editing doesn't work in a terminal",
        "A terminal has no selected text to replace, and Ctrl+C there would stop "
        "the running program.\n\n"
        "Use voice editing in text editors, word processors, browsers and chat boxes."),
    "no_selection": (
        "Select the text first",
        "Voice editing changes the text you've selected. Select it first, then hold "
        "Shift with your dictation key and say how to change it, like “make this "
        "more formal”."),
    "no_shortcuts": (
        "No bold or italics here",
        "Bold, italics and underline need a word processor like LibreOffice Writer, "
        "where TuxTalk presses Ctrl+B, Ctrl+I or Ctrl+U for you. Plain-text apps like "
        "KWrite, Kate and most chat boxes have no formatting to apply."),
    "cant_format": (
        "Voice editing changes words, not looks",
        "It can reword, shorten, fix the grammar or change capitals, but it can't "
        "change the font, size or color. Use the app's own menus for those."),
    "needs_wayland": (
        "Voice editing needs Wayland",
        "Voice editing reads the selected text through the Wayland clipboard, which an "
        "X11 session doesn't have. Log in to a Wayland session to use it. Dictation "
        "itself works the same on X11."),
}

# explained.json, next to the settings:
#   "never": kinds the user ticked "Don't explain this again" for;
#   "shown": kinds explained since the service started (start_run() clears
#            it), so each is explained once per run.
# One file, so Preferences' "Show tips again" (reset()) brings every
# explanation back at once, even with the service running.


def _never_path():
    from .config import CONFIG_PATH
    return os.path.join(os.path.dirname(CONFIG_PATH), "explained.json")


def _load():
    try:
        with open(_never_path()) as f:
            data = json.load(f)
        return {k: set(data.get(k, [])) for k in ("never", "shown")}
    except (OSError, ValueError, AttributeError, TypeError):
        return {"never": set(), "shown": set()}


def _save(data):
    try:
        with open(_never_path(), "w") as f:
            json.dump({k: sorted(v) for k, v in data.items()}, f)
    except OSError as e:
        logger.debug(f"Could not save the explained kinds: {e}")


def never_again(kind):
    """Remember that *kind* needs no more explaining (the tickbox)."""
    data = _load()
    data["never"].add(kind)
    _save(data)


def _mark_shown(kind):
    data = _load()
    data["shown"].add(kind)
    _save(data)


def start_run():
    """The service started: explain each kind once more in this run."""
    data = _load()
    if data["shown"]:
        data["shown"] = set()
        _save(data)


def reset():
    """Preferences' "Show tips again": every explanation comes back."""
    _save({"never": set(), "shown": set()})


def anything_to_reset() -> bool:
    data = _load()
    return bool(data["never"] or data["shown"])


def should_explain(kind) -> bool:
    """Whether *kind* gets the window now: it has one, it hasn't been shown
    in this run, and the user didn't tick "Don't explain this again"."""
    if kind not in EXPLANATIONS:
        return False
    data = _load()
    return kind not in data["never"] and kind not in data["shown"]


def open_window(kind) -> bool:
    """Open the explanation for *kind* in its own process. True if it was
    started; never raises."""
    _mark_shown(kind)
    env = os.environ.copy()
    # The service runs on XWayland; this window belongs on the native desktop.
    env.pop("GDK_BACKEND", None)
    try:
        from .service_launcher import dev_pythonpath
        pythonpath = dev_pythonpath()
        if pythonpath:
            env["PYTHONPATH"] = pythonpath
    except Exception:
        pass
    try:
        subprocess.Popen([sys.executable, "-m", "tuxtalk.explain", kind], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        logger.info(f"Explained: {kind}")
        return True
    except Exception as e:
        logger.warning(f"Could not open the explanation: {e}")
        return False


def build_dialog(kind):
    """The window for *kind*: (dialog, the "don't explain again" tickbox)."""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    from .ui_style import message_dialog

    title, text = EXPLANATIONS[kind]
    dialog = message_dialog(message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.NONE,
                            text=title)
    dialog.format_secondary_text(text)
    check = Gtk.CheckButton(label="Don't explain this again")
    check.set_margin_start(12)
    dialog.get_message_area().pack_start(check, False, False, 6)
    dialog.add_button("Got it", Gtk.ResponseType.OK)
    dialog.set_default_response(Gtk.ResponseType.OK)
    dialog.set_keep_above(True)
    dialog.set_position(Gtk.WindowPosition.CENTER)
    return dialog, check


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    kind = argv[0] if argv else ""
    if kind not in EXPLANATIONS:
        return 1
    try:
        from . import desktop_identity
        desktop_identity.apply()        # TuxTalk's icon on the window, not a generic one
    except Exception:
        pass
    dialog, check = build_dialog(kind)
    dialog.show_all()
    dialog.present()
    dialog.run()
    if check.get_active():
        never_again(kind)
    dialog.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())

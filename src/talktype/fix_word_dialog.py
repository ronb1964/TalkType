"""
"Fix a Word" window: teach TalkType a word from a recent dictation.

Opened from Recent Dictations in the tray menu (or the GNOME panel menu via
D-Bus). The user clicks the misheard word(s), types the right spelling, and
the fix is saved as a custom voice command (see vocabulary.py), so every
later dictation gets it right.
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from . import vocabulary
from .config import ConfigNotLoadedError
from .history import get_entries, preview
from .logger import setup_logger

logger = setup_logger(__name__)

# Singleton guard, same as the Voice Commands window: a second menu click
# brings the open window forward instead of stacking another.
_active_dialog = None

_WARNING_COLOR = "#e5a50a"


def show_fix_word_dialog(index=0, copy_text=None):
    """Open the window on recent dictation *index* (0 = newest).

    *copy_text* puts a string on the clipboard; by default clipboard.py's
    Wayland-safe copier, which works from the tray and from Preferences.
    """
    if copy_text is None:
        from .clipboard import copy_text
    global _active_dialog
    entries = get_entries()
    if _active_dialog is not None:
        _active_dialog.select_entry(index)
        from .raise_window import raise_window
        raise_window(_active_dialog.window)
        return
    if not entries:
        msg = Gtk.MessageDialog(
            message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK,
            text="No recent dictations to fix yet")
        msg.format_secondary_text(
            "Dictate something first. Then, if TalkType gets a word wrong, "
            "choose Fix a Word in the TalkType menu to teach it.")
        msg.set_keep_above(True)
        msg.run()
        msg.destroy()
        return
    _active_dialog = _FixWordDialog(entries, index, copy_text)


class _FixWordDialog:
    def __init__(self, entries, index, copy_text):
        self.entries = entries
        self.copy_text = copy_text
        self.text = ""
        self.first = self.last = None

        win = self.window = Gtk.Window(title="Fix a Word")
        win.set_default_size(560, -1)
        win.set_position(Gtk.WindowPosition.CENTER)
        win.set_keep_above(True)
        win.set_border_width(16)
        win.connect("destroy", self._on_destroy)
        win.connect("key-press-event", self._on_key)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        win.add(box)

        # Which dictation. Hidden when there is only one to choose from.
        from .ui_style import apply_dropdown_list_style
        apply_dropdown_list_style()
        self.combo = Gtk.ComboBoxText()
        for text in entries:
            self.combo.append_text(preview(text, 70))
        self.combo.connect("changed", lambda c: self._load(c.get_active()))
        if len(entries) > 1:
            row = Gtk.Box(spacing=8)
            row.pack_start(Gtk.Label(label="Dictation:"), False, False, 0)
            row.pack_start(self.combo, True, True, 0)
            box.pack_start(row, False, False, 0)

        hint = Gtk.Label(xalign=0)
        hint.set_line_wrap(True)
        hint.set_text("Click the word it got wrong, or drag across it if it's "
                      "more than one word.")
        box.pack_start(hint, False, False, 0)

        # A read-only text box rather than a button per word: it reads like
        # the sentence it is, and click-or-drag is how people select text
        # everywhere else. The selection is snapped to whole words.
        self.view = Gtk.TextView()
        self.view.set_editable(False)
        self.view.set_cursor_visible(False)
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        for side in ("left", "right", "top", "bottom"):
            getattr(self.view, f"set_{side}_margin")(8)
        # The picked words get their own highlight: the normal selection fades
        # to nearly nothing once focus moves to the "Should be" box.
        self.picked_tag = self.view.get_buffer().create_tag(
            "picked", background="#3584e4", foreground="#ffffff")
        self.view.connect("button-release-event", lambda *_: GLib.idle_add(self._on_pick))
        self.view.connect("key-release-event", lambda *_: GLib.idle_add(self._on_pick))
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_shadow_type(Gtk.ShadowType.IN)
        scroller.set_min_content_height(70)
        scroller.set_max_content_height(220)
        scroller.set_propagate_natural_height(True)
        scroller.add(self.view)
        box.pack_start(scroller, True, True, 0)

        self.heard_label = Gtk.Label(xalign=0)
        box.pack_start(self.heard_label, False, False, 0)

        row = Gtk.Box(spacing=8)
        row.pack_start(Gtk.Label(label="Should be:"), False, False, 0)
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("The right spelling, e.g. BambuStudio")
        self.entry.connect("changed", lambda _e: self._update())
        self.entry.connect("activate", lambda _e: self._on_save())
        row.pack_start(self.entry, True, True, 0)
        box.pack_start(row, False, False, 0)

        self.warning_label = Gtk.Label(xalign=0)
        self.warning_label.set_line_wrap(True)
        self.warning_label.set_no_show_all(True)
        box.pack_start(self.warning_label, False, False, 0)

        self.copy_check = Gtk.CheckButton(label="Also copy the fixed text so I can paste it")
        self.copy_check.set_active(True)
        box.pack_start(self.copy_check, False, False, 0)

        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: win.destroy())
        self.save_button = Gtk.Button(label="Always fix this")
        self.save_button.get_style_context().add_class("suggested-action")
        self.save_button.connect("clicked", lambda _b: self._on_save())
        buttons.pack_start(cancel, False, False, 0)
        buttons.pack_start(self.save_button, False, False, 0)
        box.pack_start(buttons, False, False, 0)

        self.select_entry(index)
        win.show_all()

    # --- which dictation --------------------------------------------------

    def select_entry(self, index):
        index = index if 0 <= index < len(self.entries) else 0
        if self.combo.get_active() == index:
            self._load(index)
        else:
            self.combo.set_active(index)  # fires "changed" -> _load

    def _load(self, index):
        if index < 0:
            return
        self.text = self.entries[index]
        self.first = self.last = None
        self.view.get_buffer().set_text(self.text)
        self._update()

    # --- picking words ----------------------------------------------------

    def _on_pick(self):
        """Snap whatever was clicked or dragged in the text box to whole words."""
        buf = self.view.get_buffer()
        bounds = buf.get_selection_bounds()
        if bounds:
            start, end = (it.get_offset() for it in bounds)
        else:
            start = end = buf.get_iter_at_mark(buf.get_insert()).get_offset()
        picked = vocabulary.word_range(self.text, start, end)
        buf.remove_tag(self.picked_tag, buf.get_start_iter(), buf.get_end_iter())
        if picked is None:
            self.first = self.last = None
        else:
            self.first, self.last = picked
            a, b = vocabulary.word_span(self.text, *picked)
            buf.apply_tag(self.picked_tag, buf.get_iter_at_offset(a), buf.get_iter_at_offset(b))
            # Drop the native selection so only the snapped words show.
            end_iter = buf.get_iter_at_offset(b)
            buf.select_range(end_iter, end_iter)
            self.entry.grab_focus_without_selecting()
        self._update()
        return False  # one-shot idle callback

    def _phrase(self):
        if self.first is None:
            return ""
        return vocabulary.phrase_for(self.text, self.first, self.last)

    # --- labels and the save button ----------------------------------------

    def _update(self):
        phrase = self._phrase()
        replacement = self.entry.get_text().strip()
        if phrase:
            self.heard_label.set_markup(
                f"It heard: <b>{GLib.markup_escape_text(phrase)}</b>")
        else:
            self.heard_label.set_markup("<i>No word picked yet</i>")

        warnings = []
        if phrase and vocabulary.is_risky(phrase):
            warnings.append(
                f"“{phrase}” is a common word. Saving this changes it every "
                "time you say it, not just when TalkType mishears you.")
        if phrase:
            try:
                previous = vocabulary.existing_fix(phrase)
            except Exception:
                previous = None
            if previous is not None and previous != replacement:
                warnings.append(
                    f"“{phrase}” is already fixed to “{previous}”. "
                    "Saving replaces that.")
        self._show_warning(" ".join(warnings))
        self.save_button.set_sensitive(bool(phrase and replacement and replacement != phrase))

    def _show_warning(self, text):
        if text:
            self.warning_label.set_markup(
                f'<span foreground="{_WARNING_COLOR}">{GLib.markup_escape_text(text)}</span>')
            self.warning_label.show()
        else:
            self.warning_label.hide()

    # --- saving -----------------------------------------------------------

    def _on_save(self):
        if not self.save_button.get_sensitive():
            return
        phrase = self._phrase()
        replacement = self.entry.get_text().strip()
        if vocabulary.is_risky(phrase) and not self._confirm_risky(phrase, replacement):
            return
        try:
            vocabulary.save_fix(phrase, replacement)
        except ConfigNotLoadedError:
            self._show_warning(
                "Your Voice Commands file couldn't be read, so nothing was saved. "
                "Open Preferences, Voice Commands, to check it.")
            return
        except Exception as e:
            logger.error(f"Could not save word fix: {e}")
            self._show_warning(f"Couldn't save the fix: {e}")
            return
        logger.info("Saved a word fix to custom voice commands")
        if self.copy_check.get_active():
            self.copy_text(vocabulary.fixed_text(self.text, self.first, self.last, replacement))
        self.window.destroy()

    def _confirm_risky(self, phrase, replacement):
        msg = Gtk.MessageDialog(
            transient_for=self.window, modal=True,
            message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.NONE,
            text=f"Always change “{phrase}” to “{replacement}”?")
        msg.format_secondary_text(
            f"“{phrase}” is a common word, so this will change it in every "
            "dictation, even when TalkType heard you right.")
        msg.add_button("Cancel", Gtk.ResponseType.CANCEL)
        msg.add_button("Fix it anyway", Gtk.ResponseType.OK)
        answer = msg.run()
        msg.destroy()
        return answer == Gtk.ResponseType.OK

    # --- closing ------------------------------------------------------------

    def _on_key(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.window.destroy()
            return True
        return False

    def _on_destroy(self, _widget):
        global _active_dialog
        _active_dialog = None

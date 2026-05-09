"""
TalkType Voice Commands Quick Reference — a compact cheat sheet popup.

Triggered via tray menu → "Voice Commands..." or a configurable hotkey.
Designed to be glanceable: organized by category with clear formatting.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

# Singleton guard — prevents multiple stacked dialogs
_active_dialog = None


def show_voice_commands_dialog():
    """Show a compact, quick-reference popup of all voice commands."""
    global _active_dialog
    if _active_dialog is not None:
        _active_dialog.present()
        return

    dialog = Gtk.Dialog(title="Voice Commands — Quick Reference")
    dialog.set_default_size(520, 580)
    dialog.set_resizable(True)
    dialog.set_modal(False)
    dialog.set_position(Gtk.WindowPosition.CENTER)
    dialog.set_keep_above(True)

    # Close on Escape key
    dialog.connect("key-press-event", _on_key_press)

    content = dialog.get_content_area()
    content.set_margin_top(8)
    content.set_margin_bottom(8)
    content.set_margin_start(12)
    content.set_margin_end(12)

    # Scrollable content area
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

    label = Gtk.Label()
    label.set_markup(_build_markup())
    label.set_line_wrap(True)
    label.set_xalign(0)
    label.set_valign(Gtk.Align.START)
    label.set_margin_top(8)
    label.set_margin_bottom(8)
    label.set_margin_start(12)
    label.set_margin_end(12)

    scrolled.add(label)
    content.pack_start(scrolled, True, True, 0)

    # Hotkey hint at the bottom
    hint = Gtk.Label()
    try:
        from .config import load_config
        cfg = load_config()
        hotkey = getattr(cfg, 'voice_commands_hotkey', '')
        if hotkey:
            hint.set_markup(
                f'<span size="small" color="#888888">'
                f'Tip: Press <b>{hotkey}</b> anytime to open this reference'
                f'</span>'
            )
        else:
            hint.set_markup(
                '<span size="small" color="#888888">'
                'Tip: Set a hotkey in Preferences → General to open this with a keypress'
                '</span>'
            )
    except Exception:
        hint.set_markup(
            '<span size="small" color="#888888">'
            'Tip: Set a hotkey in Preferences → General to open this with a keypress'
            '</span>'
        )
    hint.set_xalign(0.5)
    hint.set_margin_top(6)
    hint.set_margin_bottom(4)
    content.pack_start(hint, False, False, 0)

    # Close button
    close_btn = Gtk.Button(label="Close")
    close_btn.connect("clicked", lambda w: dialog.destroy())
    dialog.add_action_widget(close_btn, Gtk.ResponseType.CLOSE)
    dialog.connect("response", lambda d, r: d.destroy())

    # Clear singleton reference when dialog is closed
    def _on_destroy(widget):
        global _active_dialog
        _active_dialog = None
    dialog.connect("destroy", _on_destroy)

    _active_dialog = dialog
    dialog.show_all()
    dialog.present()


def _on_key_press(dialog, event):
    """Close dialog on Escape key."""
    if event.keyval == Gdk.KEY_Escape:
        dialog.destroy()
        return True
    return False


def _build_markup():
    """Build the Pango markup for the cheat sheet content."""
    return '''<span size="large"><b>Voice Commands</b></span>

<b>Punctuation</b>
  <b>comma</b> → ,          <b>period</b> / <b>full stop</b> → .
  <b>question mark</b> → ?    <b>exclamation point</b> → !
  <b>semicolon</b> → ;        <b>colon</b> → :
  <b>apostrophe</b> → '       <b>quote</b> → "
  <b>open quote</b> → \u201c         <b>close quote</b> → \u201d
  <b>hyphen</b> / <b>dash</b> → -    <b>em dash</b> → \u2014
  <b>ellipsis</b> / <b>dot dot dot</b> → \u2026

<b>Brackets</b>
  <b>open parenthesis</b> → (    <b>close parenthesis</b> → )
  <b>open bracket</b> → [       <b>close bracket</b> → ]
  <b>open brace</b> → {         <b>close brace</b> → }

<b>Formatting</b>
  <b>new line</b> / <b>return</b> / <b>line break</b> → line break
  <b>new paragraph</b> → double line break
  <b>tab</b> → tab character
  <b>soft break</b> → three spaces

<b>Undo</b>
  <b>undo last word</b> / <b>delete last word</b> → delete last dictated word
  <b>undo last sentence</b> / <b>delete last sentence</b> → delete back to previous sentence
  <b>undo last paragraph</b> / <b>delete last paragraph</b> → delete back to last line break
  <b>undo everything</b> / <b>delete all</b> / <b>clear all</b> → delete all dictated text

<b>Literal Words</b>
Say <b>literal</b> or <b>the word</b> before a command to type it as text:
  <b>literal period</b> → "period"    <b>literal comma</b> → "comma"
  <b>literal tab</b> → "tab"          <b>literal return</b> → "return"

<b>Custom Commands</b>
Define your own in Preferences → Commands tab.
  Wrap replacement in <b>"quotes"</b> to inject exactly as typed
  (bypasses auto-capitalization and punctuation).'''

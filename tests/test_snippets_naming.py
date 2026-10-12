"""Custom voice commands are called Snippets wherever users read about them.

"Commands" was easy to confuse with the built-in voice commands ("period",
"new line", "undo last word"). The saved file and the code keep their old
names; only the words on screen changed.
"""
import pathlib
import types

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from tuxtalk.prefs import PreferencesWindow

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "tuxtalk"


def _window(*tabs):
    notebook = Gtk.Notebook()
    for name in tabs:
        page = Gtk.Box()
        page.show()          # GtkNotebook won't switch to a hidden page
        notebook.append_page(page, Gtk.Label(label=name))
    return types.SimpleNamespace(notebook=notebook)


def test_the_preferences_tab_is_called_snippets():
    prefs = (SRC / "prefs.py").read_text()
    assert 'Gtk.Label(label="Snippets")' in prefs
    assert 'Gtk.Label(label="Commands")' not in prefs
    assert '"Add Snippet"' in prefs


def test_both_tab_names_open_snippets():
    """--tab=commands from an older launcher or script still lands there."""
    window = _window("General", "Audio", "Advanced", "Snippets", "Stats")
    for asked in ("snippets", "commands", "Commands"):
        window.notebook.set_current_page(0)
        assert PreferencesWindow.select_tab(window, asked) is True
        assert window.notebook.get_current_page() == 3


def test_help_and_quick_reference_say_snippets():
    for name in ("help_dialog.py", "voice_commands_dialog.py"):
        text = (SRC / name).read_text()
        assert "Preferences → Snippets" in text, name
        assert "Commands tab" not in text, name
        assert "Preferences → Commands" not in text, name


def test_the_snippets_tab_offers_your_words():
    prefs = (SRC / "prefs.py").read_text()
    assert 'Gtk.Button(label="Your Words...")' in prefs
    assert "custom_words.save(custom_words.parse(text))" in prefs


def test_your_words_never_opens_empty_over_an_unreadable_file():
    prefs = (SRC / "prefs.py").read_text()
    assert "custom_words.load(strict=True)" in prefs

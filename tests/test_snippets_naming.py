"""Custom voice commands are called Snippets wherever users read about them.

"Commands" was easy to confuse with the built-in voice commands ("period",
"new line", "undo last word"). The saved file and the code keep their old
names; only the words on screen say Snippets.
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


def test_the_preferences_tab_is_called_words():
    """Your Words and the Snippets share one tab, called Words."""
    prefs = (SRC / "prefs.py").read_text()
    assert 'Gtk.Label(label="Words")' in prefs
    assert 'Gtk.Label(label="Snippets")' not in prefs
    assert 'Gtk.Label(label="Commands")' not in prefs
    assert '"Add Snippet"' in prefs
    assert '"Add Word"' in prefs


def test_every_old_tab_name_opens_words():
    """--tab=commands or --tab=snippets from an older launcher or script still lands there."""
    window = _window("General", "Audio", "Advanced", "Words", "Stats")
    for asked in ("words", "snippets", "commands", "Commands"):
        window.notebook.set_current_page(0)
        assert PreferencesWindow.select_tab(window, asked) is True
        assert window.notebook.get_current_page() == 3


def test_help_and_quick_reference_say_words():
    for name in ("help_dialog.py", "voice_commands_dialog.py"):
        text = (SRC / name).read_text()
        assert "Preferences → Words" in text, name
        assert "Preferences → Snippets" not in text, name
        assert "Commands tab" not in text, name
        assert "Preferences → Commands" not in text, name


def test_the_words_tab_offers_fix_a_word_and_saves_through_vocabulary():
    prefs = (SRC / "prefs.py").read_text()
    assert 'Fix a Word...' in prefs
    assert "vocabulary.save_word(" in prefs
    assert "vocabulary.remove_word(" in prefs

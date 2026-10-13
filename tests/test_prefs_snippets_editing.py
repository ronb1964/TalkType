"""Editing the Snippets list must not save rows the user never filled in,
lose a row to a duplicate phrase, or let a write error escape OK/Apply."""
import types
from types import SimpleNamespace

from tuxtalk import prefs as P
from tuxtalk.prefs import PreferencesWindow


class FakeStore(list):
    """A ListStore stand-in: rows are lists, paths are strings like "1"."""

    def __getitem__(self, path):
        return list.__getitem__(self, int(str(path)))

    def append(self, row):
        list.append(self, list(row))
        return len(self) - 1          # the "iter"

    def get_path(self, it):
        return str(it)


def _window(rows):
    d = SimpleNamespace(commands_store=FakeStore([list(r) for r in rows]),
                        _commands_loaded={}, messages=[])
    d.commands_tree = SimpleNamespace(set_cursor=lambda *a: None, get_column=lambda i: i)
    d._message = lambda kind, title, text, buttons=None: d.messages.append(title)
    for name in ("_commands_from_store", "_fill_commands_store", "_save_custom_commands",
                 "_on_add_command", "_on_phrase_edited", "_warn_duplicate_phrase"):
        setattr(d, name, types.MethodType(getattr(PreferencesWindow, name), d))
    return d


def test_an_untouched_new_row_is_not_saved():
    """Add Snippet put the hint text into the row itself, so OK saved a live
    snippet: saying "new phrase" typed "replacement text"."""
    d = _window([["talk type", "TalkType"]])

    d._on_add_command(None)

    assert d._commands_from_store() == {"talk type": "TalkType"}


def test_a_duplicate_phrase_is_refused_and_explained(monkeypatch):
    """Two rows with one phrase saved as one, silently dropping a row."""
    monkeypatch.setattr(P.GLib, "idle_add", lambda fn, *a: fn(*a))
    d = _window([["talk type", "TalkType"], ["", ""]])

    d._on_phrase_edited(None, "1", "  Talk Type ")
    d._on_phrase_edited(None, "1", "Talk Type")   # focus-out commits it again

    assert d.commands_store[1][0] == "", "the duplicate replaced the row's phrase"
    assert "That phrase is already a snippet" in d.messages


def test_the_duplicate_warning_shows_once_per_commit(monkeypatch):
    pending = []
    monkeypatch.setattr(P.GLib, "idle_add", lambda fn, *a: pending.append(fn))
    d = _window([["talk type", "TalkType"], ["", ""]])

    d._on_phrase_edited(None, "1", "talk type")   # "edited"
    d._on_phrase_edited(None, "1", "talk type")   # and focus-out
    for fn in pending:
        fn()

    assert d.messages == ["That phrase is already a snippet"]


def test_a_row_may_keep_its_own_phrase():
    d = _window([["talk type", "TalkType"]])

    d._on_phrase_edited(None, "0", "Talk Type")

    assert d.commands_store[0][0] == "talk type"
    assert d.messages == []


def test_a_write_error_is_reported_not_raised(tmp_path, monkeypatch):
    """OSError (full disk, read-only folder) escaped from the OK handler, so
    neither the snippets nor the settings were saved and nothing was said."""
    from tuxtalk import config as C

    monkeypatch.setattr(C, "CUSTOM_COMMANDS_PATH", str(tmp_path / "custom_commands.toml"))
    monkeypatch.setattr(C, "_commands_read_failed", False, raising=False)

    def full_disk(commands):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(P, "save_custom_commands", full_disk)

    d = _window([["talk type", "TalkType"]])
    assert d._save_custom_commands() is False
    assert d.messages == ["Your snippets weren't saved"]

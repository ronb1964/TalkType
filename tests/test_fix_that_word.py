""""fix that word" opens Fix a Word over the app, on the newest dictation
(2026-10-14): learning from corrections, the way TuxTalk can, since it can't
see a word retyped by hand."""
import pytest

from tuxtalk import app, explain


@pytest.fixture
def opened(monkeypatch):
    started = []
    monkeypatch.setattr(explain, "start_helper_window", lambda module, *a: started.append(module))
    monkeypatch.setattr(app, "_beep", lambda *a: None)
    return started


@pytest.mark.parametrize("said", ["Fix that word.", "fix that", "Fix a word!", "fix the last word",
                                  "fix this word", "Fix that, please."])
def test_the_phrases_open_fix_a_word(opened, said):
    assert app._handle_fix_word(said, False) is True
    assert opened == ["tuxtalk.fix_word_dialog"]


@pytest.mark.parametrize("said", ["we need to fix that word in the report", "fix the sink",
                                  "fix", "that word"])
def test_inside_a_sentence_it_is_typed(opened, said):
    assert app._handle_fix_word(said, False) is False
    assert opened == []


def test_a_window_that_cannot_start_says_so(monkeypatch):
    notices = []
    monkeypatch.setattr(explain, "start_helper_window",
                        lambda *a: (_ for _ in ()).throw(OSError("no python")))
    monkeypatch.setattr(app, "_beep", lambda *a: None)
    monkeypatch.setattr(app, "_notify", lambda title, msg: notices.append(msg))
    assert app._handle_fix_word("fix that word", False) is True
    assert notices and "TuxTalk menu" in notices[0]


def test_the_voice_window_shows_only_the_newest_dictation(monkeypatch):
    """No dropdown: it would break on XWayland, where the window is placed."""
    pytest.importorskip("gi")
    from tuxtalk import fix_word_dialog as fw
    built = {}

    class Dialog:
        def __init__(self, entries, index, copy_text, before_show=None):
            built.update(entries=entries, before_show=before_show)
            self.window = type("W", (), {"connect": lambda *a: None, "present": lambda *a: None})()
    monkeypatch.setattr(fw, "_FixWordDialog", Dialog)
    monkeypatch.setattr(fw, "get_entries", lambda: ["newest one", "older", "oldest"])
    monkeypatch.setattr(fw.Gtk, "main", lambda: None)
    assert fw.main() == 0
    assert built["entries"] == ["newest one"]
    assert built["before_show"] is explain.place_over_active_window

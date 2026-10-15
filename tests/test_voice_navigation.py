"""Select and move by voice (TuxTalk Labs): which phrases are commands, and
the keys each one presses. See docs/superpowers/specs/2026-10-14-select-and-move-by-voice-design.md."""
import pytest

from tuxtalk import voice_navigation as nav

C, S = "CTRL", "SHIFT"


def keys(said, last=""):
    cmd = nav.parse(said)
    assert cmd is not None, f"not a command: {said!r}"
    return nav.chords(cmd, last)


# --- what is and isn't a command ----------------------------------------------------------

@pytest.mark.parametrize("said", [
    "I want to select the last sentence",      # inside a sentence: typed as text
    "go to the end of the road and turn left",
    "select the best one",
    "we should go back to the start",
    "select",
    "the end",
    "",
    "go back 11 words",                        # counts stop at 10
])
def test_not_commands(said):
    assert nav.parse(said) is None


@pytest.mark.parametrize("said", [
    "Select all.", "select all", "SELECT ALL!", "please select all", "select all please",
])
def test_punctuation_case_and_please_are_ignored(said):
    assert nav.parse(said) is not None


# --- what I just said ---------------------------------------------------------------------

@pytest.mark.parametrize("said", ["select that", "Select it.", "select what I said",
                                  "select what I just said", "select the last dictation"])
def test_select_that_selects_the_whole_last_dictation(said):
    assert keys(said, "Hello world.") == [((S,), "LEFT")] * 12


def test_a_leading_space_is_left_out():
    """Auto-space puts a space before a dictation; it stays unselected."""
    assert keys("select that", " Hello.") == [((S,), "LEFT")] * 6


def test_trailing_spaces_are_stepped_over_first():
    assert keys("select that", "Hello.\n") == [((), "LEFT")] + [((S,), "LEFT")] * 6


def test_select_the_last_sentence():
    assert keys("select the last sentence", "One thing. Two things.") == [((S,), "LEFT")] * 11


@pytest.mark.parametrize("said, n", [
    ("select the last word", 6), ("select last word", 6),
    ("select the last two words", 15), ("select the last 2 words", 15),
])
def test_select_the_last_words(said, n):
    assert keys(said, "We finished early.") == [((S,), "LEFT")] * n


def test_what_i_said_needs_something_said():
    assert nav.chords(nav.parse("select that"), "") is None
    assert nav.needs_last_text(nav.parse("select the last word"))
    assert not nav.needs_last_text(nav.parse("select all"))


# --- around the cursor --------------------------------------------------------------------

@pytest.mark.parametrize("said, expected", [
    ("select all", [((C,), "A")]),
    ("select everything", [((C,), "A")]),
    ("select the line", [((), "HOME"), ((S,), "END")]),
    ("select this line", [((), "HOME"), ((S,), "END")]),
    ("select the next word", [((C, S), "RIGHT")]),
    ("select the previous 3 words", [((C, S), "LEFT")] * 3),
    ("select the next two lines", [((S,), "DOWN")] * 2),
    ("select the previous line", [((S,), "UP")]),
    ("select to the end of the line", [((S,), "END")]),
    ("select to the start of the line", [((S,), "HOME")]),
    ("select to the beginning of the line", [((S,), "HOME")]),
    ("select to the end", [((C, S), "END")]),
    ("select to the top", [((C, S), "HOME")]),
])
def test_select_around_the_cursor(said, expected):
    assert keys(said) == expected


# --- moving -------------------------------------------------------------------------------

@pytest.mark.parametrize("said, expected", [
    ("go to the end", [((C,), "END")]),
    ("go to the bottom", [((C,), "END")]),
    ("go to the end of the document", [((C,), "END")]),
    ("go to the start", [((C,), "HOME")]),
    ("go to the beginning", [((C,), "HOME")]),
    ("go to the top", [((C,), "HOME")]),
    ("go to the end of the line", [((), "END")]),
    ("go to the start of the line", [((), "HOME")]),
    ("go back three words", [((C,), "LEFT")] * 3),
    ("go back a word", [((C,), "LEFT")]),
    ("go forward 2 words", [((C,), "RIGHT")] * 2),
    ("next word", [((C,), "RIGHT")]),
    ("previous word", [((C,), "LEFT")]),
    ("go back 5 characters", [((), "LEFT")] * 5),
    ("go forward one letter", [((), "RIGHT")]),
    ("go up two lines", [((), "UP")] * 2),
    ("go down a line", [((), "DOWN")]),
])
def test_moving(said, expected):
    assert keys(said) == expected


@pytest.mark.parametrize("said", ["unselect", "deselect", "unselect that", "clear the selection"])
def test_unselect(said):
    assert keys(said) == [((), "RIGHT")]


def test_every_command_has_a_name_for_the_log():
    assert nav.parse("go back three words").name == "go back 3 words"
    assert nav.parse("Select the last sentence.").name == "select the last sentence"


# --- in dictation (app.py) ----------------------------------------------------------------

@pytest.fixture
def dictation(monkeypatch):
    from tuxtalk import app
    seen = {"pressed": [], "problems": [], "beeps": 0}

    class Backend:
        ok = True

        def press_keys(self, chords):
            seen["pressed"].append(chords)
            return self.ok

    backend = Backend()
    monkeypatch.setattr(app, "_voice_navigation", True)
    monkeypatch.setattr(app, "_output_backend", lambda: backend)
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: "org.kde.kwrite")
    monkeypatch.setattr(app, "_edit_problem", lambda kind, beeps: seen["problems"].append(kind))
    monkeypatch.setattr(app, "_beep", lambda on, *a: seen.__setitem__("beeps", seen["beeps"] + 1))
    monkeypatch.setattr(app.state, "last_inserted_text", " We finished early.")
    seen["app"], seen["backend"] = app, backend
    return seen


def test_a_command_presses_its_keys_and_clears_undo(dictation):
    app = dictation["app"]
    assert app._handle_navigation("select the last word", False) is True
    assert dictation["pressed"] == [[((S,), "LEFT")] * 6]
    assert app.state.last_inserted_text == ""      # undo can't trust its count now
    assert dictation["beeps"] == 1 and dictation["problems"] == []


def test_ordinary_dictation_is_not_a_command(dictation):
    assert dictation["app"]._handle_navigation("we should go to the end of the road", False) is False
    assert dictation["pressed"] == []


def test_off_means_typed_as_text(dictation, monkeypatch):
    monkeypatch.setattr(dictation["app"], "_voice_navigation", False)
    assert dictation["app"]._handle_navigation("select all", False) is False


def test_a_terminal_is_refused(dictation, monkeypatch):
    app = dictation["app"]
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: "org.kde.konsole")
    assert app._handle_navigation("select all", False) is True
    assert dictation["pressed"] == [] and dictation["problems"] == ["nav_terminal"]


def test_select_that_with_nothing_dictated_says_so(dictation, monkeypatch):
    app = dictation["app"]
    monkeypatch.setattr(app.state, "last_inserted_text", "")
    assert app._handle_navigation("select that", False) is True
    assert dictation["pressed"] == [] and dictation["problems"] == ["nothing_said"]


def test_keys_that_could_not_be_pressed_say_so(dictation):
    dictation["backend"].ok = False
    assert dictation["app"]._handle_navigation("go to the end", False) is True
    assert dictation["problems"] == ["shortcut_failed"]


def test_ydotool_holds_each_modifier_around_its_key(monkeypatch):
    from tuxtalk import app
    sent = []
    monkeypatch.setattr(app, "_ydotool_key", lambda seq, **k: sent.append(seq) or True)
    assert app._send_chords([((C, S), "LEFT"), ((), "END")]) is True
    seq = sent[0]
    assert seq[2:] == ["29:1", "42:1", "105:1", "105:0", "42:0", "29:0", "107:1", "107:0"]


def test_the_setting_is_off_by_default_and_live():
    from tuxtalk import config
    assert config.Settings().voice_navigation is False
    assert "voice_navigation" in config.LIVE_APPLIED_KEYS

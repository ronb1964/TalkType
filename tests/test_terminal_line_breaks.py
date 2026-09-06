"""A line break has to be delivered differently in a terminal than in a chat app.

"new line" becomes a marker that paste mode delivers by splitting the text and
sending Shift+Enter between the chunks. That is exactly right for Claude Desktop
and other chat inputs, where a literal newline would SUBMIT the message rather
than break the line.

It is inert in a terminal. Terminals bind no soft-newline key — Enter means "run
this" — so Konsole simply ignored the keystroke and everything landed on one
line, which is what Ron reported. Verified in his log: the marker was produced
correctly and "Sending Shift+Enter after part 1" was logged, with nothing to show
for it.

Terminals accept the line break the other way round: a newline inside pasted text
is inserted literally, because bracketed paste stops the shell executing at the
first one. So in a terminal the marker becomes a real newline in one paste, and
everywhere else the existing chunk-and-keystroke path is untouched.

This is only decidable now that KWin reports the focused window on KDE; before
that a terminal was indistinguishable from anything else.
"""

import pytest

from talktype import app


@pytest.fixture
def paste_spy(monkeypatch):
    """Capture what reaches the clipboard and how many keystrokes were sent."""
    pasted = []
    breaks = []

    monkeypatch.setattr(app, "_paste_text", lambda t: pasted.append(t) or True)
    monkeypatch.setattr(app, "_send_shift_enter", lambda: breaks.append(1) or True)
    monkeypatch.setattr(app, "_type_text", lambda t: pasted.append(("typed", t)) or True)
    return pasted, breaks


class TestDeliveryPlan:
    """The decision, isolated from the injection machinery."""

    def test_a_terminal_gets_one_paste_with_a_real_newline(self):
        plan = app.plan_line_breaks("first\xa7SHIFT_ENTER\xa7second", is_terminal=True)
        assert plan == ["first\nsecond"]

    def test_a_chat_app_gets_chunks_split_for_keystrokes(self):
        plan = app.plan_line_breaks("first\xa7SHIFT_ENTER\xa7second", is_terminal=False)
        assert plan == ["first", "second"]

    def test_a_blank_line_survives_in_a_terminal(self):
        """"new paragraph" is two markers in a row."""
        text = "a\xa7SHIFT_ENTER\xa7\xa7SHIFT_ENTER\xa7b"
        assert app.plan_line_breaks(text, is_terminal=True) == ["a\n\nb"]

    def test_a_blank_line_still_becomes_two_keystrokes_elsewhere(self):
        text = "a\xa7SHIFT_ENTER\xa7\xa7SHIFT_ENTER\xa7b"
        assert app.plan_line_breaks(text, is_terminal=False) == ["a", "", "b"]

    def test_plain_text_is_one_paste_either_way(self):
        assert app.plan_line_breaks("hello", is_terminal=True) == ["hello"]
        assert app.plan_line_breaks("hello", is_terminal=False) == ["hello"]

    def test_an_existing_newline_is_kept_as_a_newline_in_a_terminal(self):
        assert app.plan_line_breaks("a\nb", is_terminal=True) == ["a\nb"]

    def test_an_existing_newline_still_splits_for_a_chat_app(self):
        assert app.plan_line_breaks("a\nb", is_terminal=False) == ["a", "b"]


class TestNoKeystrokesInATerminal:
    def test_a_terminal_receives_no_shift_enter_at_all(self, paste_spy):
        """The keystroke is inert there; sending it is pure noise."""
        pasted, breaks = paste_spy
        plan = app.plan_line_breaks("one\xa7SHIFT_ENTER\xa7two", is_terminal=True)

        assert len(plan) == 1, "a terminal must not be split into chunks"
        assert "\n" in plan[0]

    def test_a_chat_app_still_needs_one_break_between_chunks(self):
        plan = app.plan_line_breaks("one\xa7SHIFT_ENTER\xa7two", is_terminal=False)
        assert len(plan) - 1 == 1

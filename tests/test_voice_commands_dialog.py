"""The Voice Commands window lists what the code really recognises.

In 0.14.1 it left out self-corrections ("no wait", "scratch that") entirely,
showed "literal" for only four words, and didn't say the commands are English
words whatever language you dictate in.
"""
import re

from talktype import ai_cleanup, normalize, undo
from talktype.voice_commands_dialog import _build_markup

TEXT = re.sub(r"<[^>]+>", "", _build_markup()).lower()


def test_self_corrections_are_listed():
    for phrase in ("no wait", "i mean", "make that", "scratch that", "or rather"):
        assert phrase in TEXT, phrase
        assert ai_cleanup._RE_CORRECTION.search(f"at 3, {phrase}, 4"), phrase
    assert "fix self-corrections with ai" in TEXT     # it only works with that on


def test_every_clear_everything_phrase_is_listed():
    for phrase in undo.EVERYTHING_PATTERNS:
        assert phrase in TEXT, phrase


def test_alternate_wordings_are_listed_and_work():
    for phrase in ("exclamation mark", "paragraph break", "newline"):
        assert phrase in TEXT, phrase
        assert phrase in normalize.LITERAL_REPLACEMENTS
    assert undo.detect_undo_command("remove last word") == ("word", 1)
    assert "remove last" in TEXT


def test_literal_covers_every_command_word():
    assert "any punctuation or formatting word" in TEXT
    assert "the word" in TEXT


def test_says_commands_are_english_words():
    assert "english words" in TEXT

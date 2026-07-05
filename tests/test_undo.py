from talktype.undo import (
    detect_undo_command,
    calculate_undo_length,
    single_unit_length,
    EVERYTHING_PATTERNS,
    NUMBER_WORDS,
)


# ---------------------------------------------------------------------------
# detect_undo_command — pattern matching and count parsing
# ---------------------------------------------------------------------------

def test_single_word_undo():
    assert detect_undo_command("delete last word") == ("word", 1)
    assert detect_undo_command("undo last word") == ("word", 1)
    assert detect_undo_command("remove last word") == ("word", 1)
    assert detect_undo_command("delete the last word") == ("word", 1)


def test_single_sentence_undo():
    assert detect_undo_command("delete last sentence") == ("sentence", 1)
    assert detect_undo_command("undo the last sentence") == ("sentence", 1)


def test_single_paragraph_undo():
    assert detect_undo_command("delete last paragraph") == ("paragraph", 1)


def test_counted_words_word_form():
    assert detect_undo_command("delete last two words") == ("word", 2)
    assert detect_undo_command("undo last five words") == ("word", 5)
    assert detect_undo_command("remove the last ten words") == ("word", 10)


def test_counted_words_digit_form():
    assert detect_undo_command("delete last 3 words") == ("word", 3)
    assert detect_undo_command("undo last 12 words") == ("word", 12)
    assert detect_undo_command("delete the last 1 word") == ("word", 1)


def test_counted_sentences():
    assert detect_undo_command("delete last two sentences") == ("sentence", 2)
    assert detect_undo_command("undo last 4 sentences") == ("sentence", 4)


def test_counted_paragraphs():
    assert detect_undo_command("delete last three paragraphs") == ("paragraph", 3)


def test_a_an_means_one():
    # "a"/"an" are in NUMBER_WORDS so they parse as count=1 in counted form,
    # but "delete a word" (without "last") doesn't match the command regex.
    assert detect_undo_command("delete a word") is None
    assert detect_undo_command("delete last a word") == ("word", 1)
    assert detect_undo_command("undo last an sentence") == ("sentence", 1)


def test_everything_patterns_all_match():
    for phrase in EVERYTHING_PATTERNS:
        assert detect_undo_command(phrase) == ("everything", 1), phrase


def test_everything_with_punctuation():
    # Whisper output often includes punctuation/casing
    assert detect_undo_command("Delete everything.") == ("everything", 1)
    assert detect_undo_command("CLEAR ALL!") == ("everything", 1)


def test_non_undo_returns_none():
    assert detect_undo_command("hello world") is None
    assert detect_undo_command("please delete my account") is None
    assert detect_undo_command("undo this please") is None
    assert detect_undo_command("") is None


def test_number_words_table_is_complete():
    # Spot-check the table covers what's advertised in the UI (one through ten)
    for word in ["one", "two", "three", "four", "five",
                 "six", "seven", "eight", "nine", "ten"]:
        assert word in NUMBER_WORDS


# ---------------------------------------------------------------------------
# calculate_undo_length — counted iteration
# ---------------------------------------------------------------------------

def test_everything_returns_full_length():
    text = "Hello world. How are you?"
    assert calculate_undo_length(text, "everything") == len(text)
    # count is ignored for 'everything'
    assert calculate_undo_length(text, "everything", count=5) == len(text)


def test_word_single():
    # "Hello world. " — last word is "world." (trailing space ignored by rfind)
    text = "Hello world. "
    # Trailing space gets included in the cut (matches existing behavior)
    assert calculate_undo_length(text, "word") == len("world. ")


def test_word_count_two():
    text = "one two three four"  # 18 chars
    # Iter 1: removes "four" (4 chars), leaves "one two three " (trailing space).
    # Iter 2: trailing space gets included in the cut, removes "three " (6 chars).
    # Result: 10 chars total, "one two " remains.
    assert calculate_undo_length(text, "word", count=2) == 10


def test_sentence_single():
    text = "First. Second."  # 14 chars
    # Removing last sentence — back to and including the previous "."
    result = calculate_undo_length(text, "sentence")
    # Should remove " Second." (8 chars)
    assert result == 8


def test_sentence_count_two():
    text = "First. Second. Third."  # 21 chars
    # Should remove " Second. Third." (15 chars) — both back to "First."
    result = calculate_undo_length(text, "sentence", count=2)
    assert result == 15


def test_sentence_clamps_to_available():
    text = "Only sentence."
    # Asking for 5 sentences but only have 1 → return all
    assert calculate_undo_length(text, "sentence", count=5) == len(text)


def test_paragraph_with_markers():
    text = "First.§SHIFT_ENTER§Second.§SHIFT_ENTER§Third."
    # Last paragraph "Third." is after the second marker
    result = calculate_undo_length(text, "paragraph")
    assert result == len("Third.")


def test_paragraph_count_two():
    text = "First.§SHIFT_ENTER§Second.§SHIFT_ENTER§Third."
    # Removes "Third." + the marker + "Second." = 6 + 13 + 7 = 26 chars.
    # Trailing marker between "First." and "Second." is left intact, matching
    # the single-paragraph-undo convention.
    result = calculate_undo_length(text, "paragraph", count=2)
    assert result == len("Second.§SHIFT_ENTER§Third.")
    # Sanity-check the remaining text
    assert text[:-result] == "First.§SHIFT_ENTER§"


def test_paragraph_count_clamps():
    text = "First.§SHIFT_ENTER§Second.§SHIFT_ENTER§Third."
    # Asking for more than available wipes everything in the buffer
    assert calculate_undo_length(text, "paragraph", count=10) == len(text)


def test_empty_text_returns_zero():
    assert calculate_undo_length("", "word") == 0
    assert calculate_undo_length("", "sentence", count=3) == 0
    assert calculate_undo_length("", "everything") == 0


def test_zero_or_negative_count_returns_zero():
    assert calculate_undo_length("hello world", "word", count=0) == 0
    assert calculate_undo_length("hello world", "word", count=-1) == 0


# ---------------------------------------------------------------------------
# single_unit_length — boundary detection sanity
# ---------------------------------------------------------------------------

def test_single_unit_word_no_space():
    # No space in text → whole thing is the "last word"
    assert single_unit_length("oneword", "word") == 7


def test_single_unit_unknown_type():
    assert single_unit_length("text", "bogus") == 0


# =====================================================================
# v0.5.17 review fixes — the undo buffer now stores line breaks as '\n'
# (one char = one backspace), so word boundaries must treat newlines
# and tabs as separators, not as part of the word.
# =====================================================================

def test_word_boundary_at_newline():
    """'hello\\nworld' — last word is 'world' (5 chars), not the whole string."""
    assert single_unit_length("hello\nworld", "word") == 5


def test_word_boundary_at_tab():
    assert single_unit_length("hello\tworld", "word") == 5


def test_paragraph_length_with_newline_breaks():
    """Guard: '\\n'-separated paragraphs measure correctly."""
    assert calculate_undo_length("first\nsecond", "paragraph", 1) == 6

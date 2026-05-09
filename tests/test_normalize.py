from talktype.normalize import normalize_text

def test_basic_punct():
    s = "thank you comma this is great exclamation point"
    assert normalize_text(s) == "Thank you, this is great!"

def test_space_before_bang_removed():
    s = "thank you very much !"
    assert normalize_text(s) == "Thank you very much!"

def test_quotes_and_comma():
    # "open quote ... close quote" preserves inner text as literal
    # (punctuation commands are NOT processed inside quotes).
    # The exclamation point lands outside the closing quote.
    s = "open quote hello comma world close quote exclamation point"
    assert normalize_text(s) == '"hello comma world"!'

def test_ellipsis_and_caps():
    s = "this is fine dot dot dot next sentence"
    # Note: auto-period adds period at end of line
    assert normalize_text(s) == "This is fine\u2026 Next sentence."

def test_newlines_tabs():
    s = "first line newline tab indented second line period"
    # Note: \u00a7SHIFT_ENTER\u00a7 markers are converted to keypresses by app.py
    # Auto-period adds periods at line ends
    # There's a space after tab because capitalize logic adds it
    assert normalize_text(s) == "First line.\u00a7SHIFT_ENTER\u00a7\t Indented second line."

def test_return_commands():
    """Test various voice commands for line breaks"""
    # Test "return" - returns \u00a7SHIFT_ENTER\u00a7 markers, auto-adds periods
    # Space after marker due to normalize logic
    s = "first line return second line"
    assert normalize_text(s) == "First line.\u00a7SHIFT_ENTER\u00a7 Second line."

    # Test "line break"
    s = "first line line break second line"
    assert normalize_text(s) == "First line.\u00a7SHIFT_ENTER\u00a7 Second line."

    # Test "new paragraph" for double line break
    # Note: the regex for "new paragraph" eats surrounding whitespace/punctuation,
    # so no space appears after the second marker.
    s = "first paragraph new paragraph second paragraph"
    assert normalize_text(s) == "First paragraph.\u00a7SHIFT_ENTER\u00a7\u00a7SHIFT_ENTER\u00a7Second paragraph."

    # Test "paragraph break"
    s = "first paragraph paragraph break second paragraph"
    assert normalize_text(s) == "First paragraph.\u00a7SHIFT_ENTER\u00a7\u00a7SHIFT_ENTER\u00a7Second paragraph."


# =====================================================================
# Context-aware protection: command words used as English nouns must
# NOT be replaced with punctuation. Bug pattern: phrases like "period
# of time" became "period. Of time" because the regex matched any
# occurrence of the word.
# =====================================================================

def test_period_of_time_preserved():
    """'period of [noun]' is a fixed noun phrase, not a sentence terminator."""
    s = "we waited a fairly long period of time"
    assert normalize_text(s) == "We waited a fairly long period of time."

def test_period_after_adjective_preserved():
    """'[adjective] period' is noun usage."""
    s = "during a brief period"
    assert normalize_text(s) == "During a brief period."

def test_period_after_article_preserved():
    """'the/this/that period' is noun usage."""
    s = "the period was difficult"
    assert normalize_text(s) == "The period was difficult."

def test_period_still_works_as_command():
    """End-of-clause 'period' still acts as sentence terminator."""
    s = "I am going home period new sentence here"
    assert normalize_text(s) == "I am going home. New sentence here."

def test_in_return_preserved():
    """'in return' is a fixed phrase, not a line break command."""
    s = "he gave me nothing in return"
    assert normalize_text(s) == "He gave me nothing in return."

def test_tax_return_preserved():
    """'tax return' should not become 'tax [line break]'."""
    s = "I filed my tax return yesterday"
    assert normalize_text(s) == "I filed my tax return yesterday."

def test_his_return_preserved():
    """Possessive + return is noun usage."""
    s = "we celebrated his return home"
    assert normalize_text(s) == "We celebrated his return home."

def test_return_still_works_as_line_break():
    """Bare 'return' between clauses still acts as line break."""
    s = "first line return second line"
    assert normalize_text(s) == "First line.\u00a7SHIFT_ENTER\u00a7 Second line."

def test_dash_of_salt_preserved():
    """'dash of [word]' is recipe/measurement noun usage."""
    s = "add a dash of salt to the recipe"
    assert normalize_text(s) == "Add a dash of salt to the recipe."

def test_dash_still_works_as_command():
    """'X dash Y' between words still produces a hyphen."""
    s = "well dash known author"
    # "dash" between words \u2192 hyphen, "well-known" gets joined
    assert "well-known" in normalize_text(s).lower()

def test_great_quote_preserved():
    """'[adjective] quote' is noun usage."""
    s = "she said a great quote about life"
    assert normalize_text(s) == "She said a great quote about life."

def test_comma_operator_preserved():
    """'comma operator' is a programming term, not a punctuation command."""
    s = "the comma operator in C is useful"
    assert normalize_text(s) == "The comma operator in C is useful."

def test_comma_still_works_between_clauses():
    """Bare 'comma' between phrases still produces a comma."""
    s = "first item comma second item comma third item"
    assert normalize_text(s) == "First item, second item, third item."


# =====================================================================
# Standalone-"i" capitalization. Whisper transcribes the pronoun "I"
# as lowercase when it appears mid-sentence; cap_first only handles
# the first letter of a line, so mid-sentence occurrences slip through.
# =====================================================================

def test_standalone_i_capitalized_midsentence():
    """Lowercase 'i' as a standalone pronoun mid-sentence becomes 'I'."""
    s = "today i went to the store"
    assert normalize_text(s) == "Today I went to the store."

def test_multiple_standalone_i_capitalized():
    """All standalone 'i' occurrences in one sentence get capitalized."""
    s = "i think i can do it"
    assert normalize_text(s) == "I think I can do it."

def test_i_contraction_capitalized_midsentence():
    """'i'll', 'i'm', 'i've', 'i'd' mid-sentence get capitalized."""
    s = "tomorrow i'll go and i'm sure i've earned it"
    assert normalize_text(s) == "Tomorrow I'll go and I'm sure I've earned it."

def test_words_containing_i_not_touched():
    """Words like 'in', 'it', 'iPad' must NOT be altered."""
    s = "the iPad is in it"
    # cap_first capitalizes the leading 'T' of "the"; "iPad", "in", "it" untouched
    assert normalize_text(s) == "The iPad is in it."

def test_existing_uppercase_I_unchanged():
    """An already-capitalized 'I' is left alone (no double processing)."""
    s = "I already said I would"
    assert normalize_text(s) == "I already said I would."

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

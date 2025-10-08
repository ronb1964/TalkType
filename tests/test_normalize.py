from talktype.normalize import normalize_text

def test_basic_punct():
    s = "thank you comma this is great exclamation point"
    assert normalize_text(s) == "Thank you, this is great!"

def test_space_before_bang_removed():
    s = "thank you very much !"
    assert normalize_text(s) == "Thank you very much!"

def test_quotes_and_comma():
    s = "open quote hello comma world close quote exclamation point"
    assert normalize_text(s) == "“Hello, world!”"

def test_ellipsis_and_caps():
    s = "this is fine dot dot dot next sentence"
    # Note: auto-period adds period at end of line
    assert normalize_text(s) == "This is fine… Next sentence."

def test_newlines_tabs():
    s = "first line newline tab indented second line period"
    # Note: §SHIFT_ENTER§ markers are converted to keypresses by app.py
    # Auto-period adds periods at line ends
    # There's a space after tab because capitalize logic adds it
    assert normalize_text(s) == "First line.§SHIFT_ENTER§\t Indented second line."

def test_return_commands():
    """Test various voice commands for line breaks"""
    # Test "return" - returns §SHIFT_ENTER§ markers, auto-adds periods
    # Space after marker due to normalize logic
    s = "first line return second line"
    assert normalize_text(s) == "First line.§SHIFT_ENTER§ Second line."

    # Test "line break"
    s = "first line line break second line"
    assert normalize_text(s) == "First line.§SHIFT_ENTER§ Second line."

    # Test "new paragraph" for double line break
    s = "first paragraph new paragraph second paragraph"
    assert normalize_text(s) == "First paragraph.§SHIFT_ENTER§§SHIFT_ENTER§ Second paragraph."

    # Test "paragraph break"
    s = "first paragraph paragraph break second paragraph"
    assert normalize_text(s) == "First paragraph.§SHIFT_ENTER§§SHIFT_ENTER§ Second paragraph."

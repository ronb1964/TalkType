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


# =====================================================================
# v0.5.17 review fixes — regression tests for verified corruption bugs.
# Each case below was reproduced against the pre-fix code during the
# 2026-07-04 full-codebase review.
# =====================================================================

def test_decimals_and_prices_preserved():
    """Periods inside numbers must not get split: '3.5' stayed '3. 5' before fix."""
    assert normalize_text("version 3.5 costs $19.99") == "Version 3.5 costs $19.99."


def test_single_letter_abbreviations_preserved():
    """'U.S.' / 'e.g.' must not be split into 'U. S.' / 'e. G.'"""
    assert normalize_text("the U.S. economy grew") == "The U.S. economy grew."
    assert normalize_text("this is useful e.g. when testing") == "This is useful e.g. when testing."


def test_am_prefixed_words_not_time_formatted():
    """Number + word starting with 'am'/'pm' must not be treated as a time."""
    assert normalize_text("there are 5 among us") == "There are 5 among us."
    assert normalize_text("I ate 3 amazing tacos") == "I ate 3 amazing tacos."


def test_time_formatting_still_works():
    """Real times keep getting normalized (guard for the am/pm fix)."""
    assert "11:30 PM" in normalize_text("meet me at 11. 30 p. m. sharp")
    assert "5 PM" in normalize_text("the store closes at 5 p. m. tonight")


def test_em_dash_command_works():
    """'em dash' was broken: the 'dash' rule ran first, leaving 'em-'."""
    assert normalize_text("please use an em dash here") == "Please use an — here."


def test_dash_command_still_works():
    """Plain 'dash' still produces a tight hyphen (guard for the reorder)."""
    assert normalize_text("five dash three") == "Five-three."


def test_return_verb_not_treated_as_command():
    """Common verb uses of 'return' must not insert a line break."""
    out = normalize_text("I want to return this item tomorrow")
    assert "§SHIFT_ENTER§" not in out
    assert "return this item" in out

    out = normalize_text("she will return next week")
    assert "§SHIFT_ENTER§" not in out
    assert "will return" in out

    out = normalize_text("please return it to the store")
    assert "§SHIFT_ENTER§" not in out


def test_tab_noun_not_treated_as_command():
    """Common noun uses of 'tab' must not insert a tab character."""
    out = normalize_text("open a new tab in the browser")
    assert "\t" not in out
    assert "tab" in out

    out = normalize_text("press the tab key to indent")
    assert "\t" not in out
    assert "tab key" in out


def test_tab_command_still_works():
    """Bare 'tab' at the start of dictation still produces a tab character."""
    assert normalize_text("tab hello world").startswith("\t")


# --- append_auto_punct: auto-period/space placement around line-break markers ---

from talktype.normalize import append_auto_punct

_M = "§SHIFT_ENTER§"


def test_auto_punct_plain_text():
    assert append_auto_punct("Hello world", True, True) == "Hello world. "
    assert append_auto_punct("Hello world.", True, True) == "Hello world. "
    assert append_auto_punct("Hello", False, False) == "Hello"


def test_auto_punct_no_orphan_period_after_trailing_break():
    """'hello new line' used to become 'Hello.' + newline + '. ' (orphan)."""
    assert append_auto_punct(f"Hello.{_M}", True, True) == f"Hello.{_M}"


def test_auto_punct_period_goes_before_trailing_break():
    assert append_auto_punct(f"Hello{_M}", True, True) == f"Hello.{_M}"
    assert append_auto_punct(f"Hello{_M}{_M}", True, True) == f"Hello.{_M}{_M}"


def test_auto_punct_only_markers_untouched():
    assert append_auto_punct(_M, True, True) == _M


# --- Adversarial-review regressions: protection lists must not swallow the command ---

def test_return_command_after_pronoun_still_works():
    """'thank you return' is a very common dictation ending — must break line."""
    assert normalize_text("thank you return") == f"Thank you.{_M}"


def test_return_command_before_sentence_starter_still_works():
    """Utterance-initial 'return' followed by a normal sentence must break + capitalize."""
    out = normalize_text("return this is a test")
    assert _M in out
    assert "This is a test." in out


def test_tab_field_separator_still_works():
    """'first tab second tab third' — tab as field separator must keep working."""
    assert normalize_text("first tab second tab third").count("\t") == 2


def test_line_starting_with_protected_word_is_capitalized():
    """A protected word at line start must still get sentence capitalization."""
    assert normalize_text("return to sender was my favorite song") == "Return to sender was my favorite song."


# --- cap_first: don't capitalize past the start of the line -----------------
# The capitalization pass scanned forward to the first letter it could find,
# so a line opening with a number or symbol capitalized the *second* word.

def test_line_starting_with_a_year_does_not_capitalize_the_next_word():
    assert normalize_text("2024 was a good year") == "2024 was a good year."


def test_line_starting_with_a_price_does_not_capitalize_the_next_word():
    assert normalize_text("$50 is too much") == "$50 is too much."


def test_line_starting_with_a_count_does_not_capitalize_the_next_word():
    assert normalize_text("15 minutes later he left") == "15 minutes later he left."


def test_email_address_at_line_start_is_not_capitalized():
    assert normalize_text("rbrand@example.com is my email") == "rbrand@example.com is my email."


def test_url_at_line_start_is_not_capitalized():
    assert normalize_text("github.com/ronb1964 has the code") == "github.com/ronb1964 has the code."


def test_opening_quote_is_still_skipped_when_capitalizing():
    assert normalize_text('"hello there" she said') == '"Hello there" she said.'


def test_ordinary_sentences_are_still_capitalized():
    assert normalize_text("the meeting went well") == "The meeting went well."


# --- a.m./p.m. must not swallow the sentence period -------------------------
# "a.m." ends in a period that can also be the full stop. Rewriting it to "AM"
# dropped that period, merging two sentences into one.

def test_am_at_end_of_text_keeps_its_period():
    assert normalize_text("It starts at 5 p.m.") == "It starts at 5 PM."


def test_am_mid_text_does_not_gain_a_period_even_before_a_capital():
    """Deliberate limitation, documented rather than guessed at.

    "9 a.m. We should be early" and "8 a.m. Tuesday" are grammatically
    identical, and a following capital cannot tell them apart because Whisper
    capitalizes proper nouns as well as sentence starts. Adding a period here
    split ordinary sentences in two, which is worse than leaving one out: a
    wrong split corrupts text the user must notice and repair, while a missing
    full stop merely reads a little short.
    """
    assert normalize_text("The meeting is at 9 a.m. We should be early.") == \
        "The meeting is at 9 AM We should be early."


def test_am_with_minutes_mid_text_does_not_gain_a_period():
    assert normalize_text("Dinner is at 7:30 p.m. Bring a dish.") == \
        "Dinner is at 7:30 PM Bring a dish."


def test_am_mid_sentence_does_not_gain_a_period():
    assert normalize_text("Call me at 9 a.m. tomorrow if you can.") == \
        "Call me at 9 AM tomorrow if you can."


def test_am_followed_by_a_lowercase_word_does_not_gain_a_period():
    assert normalize_text("I woke at 6 a.m. and went running.") == \
        "I woke at 6 AM and went running."


# --- regression: a.m./p.m. must not split a sentence at a proper noun -------
# Whisper capitalizes proper nouns as well as sentence starts, so "uppercase
# word follows" is not evidence that the abbreviation's period was also a full
# stop. "8 a.m. Tuesday" is an ordinary thing to dictate.

def test_am_before_a_weekday_does_not_gain_a_period():
    assert normalize_text("we start at 8 a.m. Tuesday") == "We start at 8 AM Tuesday."


def test_pm_before_a_weekday_does_not_gain_a_period():
    assert normalize_text("the deadline is 5 p.m. Friday") == "The deadline is 5 PM Friday."


def test_am_before_a_month_does_not_gain_a_period():
    assert normalize_text("the 8 a.m. January review") == "The 8 AM January review."


def test_pm_before_a_timezone_does_not_gain_a_period():
    assert normalize_text("call me at 5 p.m. EST") == "Call me at 5 PM EST."


def test_am_mid_sentence_before_a_capitalized_word_does_not_gain_a_period():
    assert normalize_text("the 9 a.m. Monday meeting is cancelled") == \
        "The 9 AM Monday meeting is cancelled."


# --- filenames must not be split into two sentences -------------------------

def test_a_filename_is_not_split_into_two_sentences():
    """The pass that puts a space after a sentence period protected decimals
    ("19.99") and single-letter abbreviations ("e.g."), and a separate guard
    protects domains ("example.com"). Filenames had neither, so "report.pdf"
    became "report. Pdf" — the extension capitalized as a new sentence."""
    assert normalize_text("the file is report.pdf") == "The file is report.pdf."


def test_common_file_extensions_survive():
    for name in ("notes.txt", "photo.jpeg", "archive.tar", "script.py",
                 "sheet.xlsx", "song.mp3", "readme.md"):
        out = normalize_text(f"open {name} now")
        assert name in out, f"{name} was mangled into {out!r}"


def test_a_domain_still_survives():
    """Already worked — pin it so the filename fix doesn't regress it."""
    assert "example.com" in normalize_text("go to example.com for info")


def test_a_real_sentence_boundary_is_still_spaced():
    """The guard must not stop genuine missing-space repairs."""
    assert normalize_text("this is one.this is two") == "This is one. This is two."


# --- i.e. is not the pronoun "I" --------------------------------------------

def test_ie_is_not_capitalized_as_the_pronoun():
    """The standalone-"i" rule uses \\bi\\b, and the dot in "i.e." is a word
    boundary — so "i.e." became "I.e." in the middle of a sentence."""
    assert normalize_text("use it, i.e. the new one") == "Use it, i.e. the new one."


def test_the_pronoun_i_is_still_capitalized():
    assert normalize_text("then i went home") == "Then I went home."


def test_i_at_the_end_of_a_sentence_is_still_capitalized():
    assert normalize_text("that was me and i") == "That was me and I."


# --- a line already ending in punctuation gets no extra period --------------

def test_a_line_ending_in_a_colon_gets_no_period():
    """"[.?!…]" was the whole definition of "already punctuated", so a
    dictated colon or semicolon collected a period: "the plan:." """
    assert normalize_text("here is the plan colon") == "Here is the plan:"


def test_a_line_ending_in_a_semicolon_gets_no_period():
    assert normalize_text("first do this semicolon") == "First do this;"


# --- times must not capitalize the word that follows -------------------------

def test_a_spaced_am_does_not_capitalize_the_next_word():
    """Whisper writes "9 a. m.". Time formatting collapsed that to "9 AM",
    but it ran AFTER the capitalization pass — which had already treated the
    "m." as a sentence ending and upper-cased the following word."""
    assert normalize_text("meet at 9 a. m. tomorrow") == "Meet at 9 AM tomorrow."


def test_a_spaced_pm_does_not_capitalize_the_next_word():
    assert normalize_text("it was 5 p. m. and dark") == "It was 5 PM and dark."


def test_a_time_with_minutes_still_formats():
    assert "11:30 PM" in normalize_text("the meeting is at 11. 30 p. m. sharp")


def test_a_time_ending_the_sentence_keeps_its_period():
    """Pinned behaviour: the abbreviation's dot doubles as the full stop."""
    assert normalize_text("we start at 8 a. m.") == "We start at 8 AM."


# --- append_auto_punct edge cases ------------------------------------------

from talktype.normalize import append_auto_punct


def test_auto_punct_leaves_a_trailing_colon_alone():
    assert append_auto_punct("here is the plan:", True, False) == "here is the plan:"


def test_auto_punct_leaves_a_trailing_semicolon_alone():
    assert append_auto_punct("first do this;", True, False) == "first do this;"


def test_auto_punct_does_not_invent_a_period_from_silence():
    """A whitespace-only utterance became a lone "." injected into the
    document — a stray full stop appearing from a recording of nothing."""
    assert append_auto_punct("   ", True, False).strip() == ""


def test_auto_punct_still_adds_a_period_to_a_normal_sentence():
    assert append_auto_punct("this is a sentence", True, False) == "this is a sentence."


# --- the auto-period preference must actually be honoured -------------------

def test_normalize_can_be_told_not_to_add_a_period():
    """normalize_text appended a full stop to every line unconditionally, and
    _prepare_text calls it BEFORE append_auto_punct — so the "Ensure period at
    end of sentences" preference had no effect at all when unchecked: the
    period was already there by the time the preference was consulted."""
    assert normalize_text("this is a sentence", auto_period=False) == "This is a sentence"


def test_normalize_adds_a_period_by_default():
    assert normalize_text("this is a sentence") == "This is a sentence."


def test_auto_period_off_still_normalizes_everything_else():
    """Turning the period off must not turn off capitalization or spacing."""
    out = normalize_text("hello comma world", auto_period=False)
    assert out == "Hello, world"

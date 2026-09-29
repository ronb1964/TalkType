"""Teaching TalkType a word from a recent dictation (Recent Dictations > Fix a Word).

The fix is saved as an ordinary custom voice command ("bamboo studio" =
"BambuStudio"), so it works for every engine: it rewrites the transcription
after the model heard it, which Parakeet has no other way to take.
"""

import pytest

from talktype import config, vocabulary


# --- which words were picked -------------------------------------------------

def test_words_are_split_on_whitespace():
    assert vocabulary.words("I ordered filament, for the  printer.") == [
        "I", "ordered", "filament,", "for", "the", "printer."]


@pytest.mark.parametrize("text, first, last, phrase", [
    ("I use bamboo studio daily", 2, 3, "bamboo studio"),
    ("Open Bamboo Studio.", 1, 2, "bamboo studio"),        # case and full stop
    ("He said \"gift tarot\", then left", 2, 3, "gift tarot"),  # quotes and comma
    ("why do tool works", 0, 2, "why do tool"),
    ("it's fine", 0, 0, "it's"),                             # inner apostrophe kept
])
def test_phrase_is_the_selection_lowercased_without_edge_punctuation(text, first, last, phrase):
    assert vocabulary.phrase_for(text, first, last) == phrase


def test_selection_order_does_not_matter():
    assert vocabulary.phrase_for("a b c d", 3, 1) == "b c d"


def test_selection_of_only_punctuation_gives_empty_phrase():
    assert vocabulary.phrase_for("well -- okay", 1, 1) == ""


# --- the corrected dictation -------------------------------------------------

def test_fixed_text_replaces_the_words_and_keeps_surrounding_punctuation():
    text = "I opened Bamboo Studio, then printed."
    assert vocabulary.fixed_text(text, 2, 3, "BambuStudio") == \
        "I opened BambuStudio, then printed."


def test_fixed_text_keeps_quotes_and_the_rest_untouched():
    text = 'He said "gift tarot" twice.\nNext line stays.'
    assert vocabulary.fixed_text(text, 2, 3, "Giftara") == \
        'He said "Giftara" twice.\nNext line stays.'


def test_fixed_text_keeps_original_spacing_elsewhere():
    assert vocabulary.fixed_text("one  two three", 2, 2, "3") == "one  two 3"


# --- when to warn ------------------------------------------------------------

@pytest.mark.parametrize("phrase", ["the", "four", "and", "is", "you"])
def test_common_single_words_need_a_warning(phrase):
    assert vocabulary.is_risky(phrase)


@pytest.mark.parametrize("phrase", ["bamboo studio", "ydotool", "giftara", "the van"])
def test_uncommon_words_and_phrases_do_not(phrase):
    assert not vocabulary.is_risky(phrase)


# --- saving ------------------------------------------------------------------

@pytest.fixture
def commands_file(tmp_path, monkeypatch):
    path = tmp_path / "custom_commands.toml"
    monkeypatch.setattr(config, "CUSTOM_COMMANDS_PATH", str(path))
    return path


def test_save_adds_to_existing_voice_commands(commands_file):
    config.save_custom_commands({"my email address": "me@example.com"})

    previous = vocabulary.save_fix("bamboo studio", "BambuStudio")

    assert previous is None
    assert config.load_custom_commands() == {
        "my email address": "me@example.com",
        "bamboo studio": "BambuStudio",
    }


def test_save_reports_what_it_replaced(commands_file):
    config.save_custom_commands({"gift tarot": "Giftarot"})

    assert vocabulary.save_fix("gift tarot", "Giftara") == "Giftarot"
    assert config.load_custom_commands() == {"gift tarot": "Giftara"}


def test_existing_fix_is_found_before_saving(commands_file):
    config.save_custom_commands({"gift tarot": "Giftarot"})
    assert vocabulary.existing_fix("gift tarot") == "Giftarot"
    assert vocabulary.existing_fix("bamboo studio") is None


def test_save_refuses_when_the_commands_file_is_unreadable(commands_file):
    commands_file.write_text("this is [not valid toml")

    with pytest.raises(config.ConfigNotLoadedError):
        vocabulary.save_fix("bamboo studio", "BambuStudio")

    assert commands_file.read_text() == "this is [not valid toml"


def test_saved_fix_is_applied_to_the_next_dictation(commands_file, monkeypatch):
    """End to end with the dictation service's own matcher."""
    from talktype import app

    vocabulary.save_fix("bamboo studio", "BambuStudio")
    monkeypatch.setattr(app, "_custom_commands", config.load_custom_commands())

    text, _protected = app._apply_custom_commands("i opened Bamboo Studio today")
    assert text == "i opened BambuStudio today"


# --- mapping a click or drag in the text box to whole words -------------------

@pytest.mark.parametrize("start, end, expected", [
    (10, 10, (2, 2)),    # click inside "Bamboo"
    (9, 9, (2, 2)),      # click right at its first letter
    (15, 15, (2, 2)),    # click right after its last letter
    (11, 18, (2, 3)),    # drag from inside "Bamboo" into "Studio"
    (18, 11, (2, 3)),    # dragged backwards
    (3, 40, (1, 5)),     # sloppy drag snaps to whole words
])
def test_word_range_snaps_clicks_and_drags_to_whole_words(start, end, expected):
    text = "I opened Bamboo Studio, then printed."
    #       0 2      9     16     23   28
    assert vocabulary.word_range(text, start, end) == expected


def test_word_range_is_none_when_nothing_is_under_the_click():
    assert vocabulary.word_range("one   two", 4, 4) is None
    assert vocabulary.word_range("", 0, 0) is None


def test_word_span_covers_the_picked_words():
    text = "I opened Bamboo Studio, then printed."
    assert vocabulary.word_span(text, 2, 3) == (9, 23)

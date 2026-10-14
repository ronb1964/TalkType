"""Write numbers as digits: "twenty-five" becomes "25" (Discussion #11).

Parakeet writes small numbers and dates as words ("three cats", "october
fifteenth"); Whisper mostly writes digits. The option turns spoken numbers into
digits in the finished text, so it works the same with every engine. A second
choice keeps one to nine as words, the way many style guides write them.
"""
import pytest

from tuxtalk import app, config
from tuxtalk.spoken_numbers import SUPPORTED_LANGUAGES, to_digits


@pytest.mark.parametrize("text, expected", [
    # What Parakeet really typed in the 2026-10-14 test.
    ("I have three cats and twenty-five chickens.", "I have 3 cats and 25 chickens."),
    ("The meeting is on october fifteenth.", "The meeting is on october 15th."),
    ("It costs one hundred and fifty dollars.", "It costs 150 dollars."),
    ("Ninety-nine bottles", "99 bottles"),
    ("Version two point five is out.", "Version 2.5 is out."),
    ("Give me forty two percent.", "Give me 42 percent."),
    ("the twenty first time", "the 21st time"),
    # Numbers are left alone where they aren't counting anything.
    ("One of them said no one would come, on the one hand.",
     "One of them said no one would come, on the one hand."),
    ("We need a one-off fix.", "We need a one-off fix."),
    ("I'll take the second one.", "I'll take the second one."),
    ("He was the first to call.", "He was the first to call."),
    ("That's one small step.", "That's one small step."),
    # Fractions stay words: "two 3rds" reads wrong.
    ("It's two thirds full.", "It's two thirds full."),
    ("a third of it, one third of it", "a third of it, one third of it"),
    ("three quarters of an hour", "three quarters of an hour"),
    # "a hundred people" stays as said, rather than "a 100 people".
    ("a hundred people, a thousand times", "a hundred people, a thousand times"),
    # Digits read out one at a time join up into one number.
    ("My zip code is zero eight six two zero.", "My zip code is 08620."),
    ("call five five five one two three four", "call 5551234"),
    # A list keeps its commas.
    ("three, four, five", "3, 4, 5"),
    # Years.
    ("It was nineteen eighty four.", "It was 1984."),
    ("back in twenty twenty five", "back in 2025"),
    ("built in nineteen oh five", "built in 1905"),
    # Times.
    ("Meet me at seven thirty.", "Meet me at 7:30."),
    ("at seven fifteen pm", "at 7:15 PM"),
    ("Parakeet wrote at 7 30 by itself", "Parakeet wrote at 7:30 by itself"),
    # Already digits: nothing to do.
    ("It costs $150 and 2,400 units.", "It costs $150 and 2,400 units."),
    ("", ""),
])
def test_english(text, expected):
    assert to_digits(text, "en") == expected


@pytest.mark.parametrize("text, expected", [
    ("I have three cats and twenty-five chickens.", "I have three cats and 25 chickens."),
    ("nine lives, ten lives", "nine lives, 10 lives"),
    ("page eleven", "page 11"),
    ("the third time, the eleventh hour", "the third time, the 11th hour"),
    # Digits read one at a time are a number however small each one is.
    ("zero eight six two zero", "08620"),
    ("Meet me at seven thirty.", "Meet me at 7:30."),
])
def test_one_to_nine_stay_words(text, expected):
    assert to_digits(text, "en", small_as_words=True) == expected


@pytest.mark.parametrize("text, lang, expected", [
    ("Die Straße ist dreiundzwanzig Meter lang", "de", "Die Straße ist 23 Meter lang"),
    ("Tengo veinticinco años y tres gatos", "es", "Tengo 25 años y 3 gatos"),
    ("J'ai vingt-cinq ans", "fr", "J'ai 25 ans"),
])
def test_other_languages(text, lang, expected):
    assert to_digits(text, lang) == expected


def test_an_unsupported_language_is_left_alone():
    assert "ja" not in SUPPORTED_LANGUAGES
    assert to_digits("three cats", "ja") == "three cats"
    assert to_digits("three cats", "") == "three cats"


def test_a_region_code_still_counts():
    """"en_US" or "pt-BR" from a locale is English or Portuguese."""
    assert to_digits("three cats", "en_US") == "3 cats"
    assert to_digits("três gatos", "pt-BR") == "3 gatos"


def test_off_by_default():
    assert config.Settings().numbers_as_digits is False
    assert config.Settings().numbers_small_as_words is False


def test_it_applies_without_a_restart():
    assert "numbers_as_digits" in config.LIVE_APPLIED_KEYS
    assert "numbers_small_as_words" in config.LIVE_APPLIED_KEYS


def _prepare(monkeypatch, mode, raw="i have three cats and twenty five chickens"):
    monkeypatch.setattr(app, "_numbers_mode", mode)
    monkeypatch.setattr(app, "_numbers_language", "en")
    monkeypatch.setattr(app, "_custom_words", [])
    monkeypatch.setattr(app, "_remove_fillers", False)
    monkeypatch.setattr(app, "_ai_corrections", False)
    monkeypatch.setattr(app, "_swiss_spelling", False)
    return app._prepare_text(raw, smart_quotes=True, auto_period=True, auto_space=False)


def test_dictation_uses_digits_when_on(monkeypatch):
    assert _prepare(monkeypatch, "all") == "I have 3 cats and 25 chickens."


def test_dictation_keeps_small_numbers_as_words_when_asked(monkeypatch):
    assert _prepare(monkeypatch, "small_as_words") == "I have three cats and 25 chickens."


def test_dictation_is_unchanged_when_off(monkeypatch):
    assert "three" in _prepare(monkeypatch, None)


def test_settings_pick_the_mode_and_language(monkeypatch):
    # Put back whatever the other tests expect once this one is done.
    monkeypatch.setattr(app, "_numbers_mode", None)
    monkeypatch.setattr(app, "_numbers_language", "en")
    monkeypatch.setattr(app, "_ai_engine", None)
    cfg = config.Settings()
    cfg.numbers_as_digits = True
    cfg.dictation_language = "de"
    app._apply_cleanup_settings(cfg)
    assert app._numbers_mode == "all"
    assert app._numbers_language == "de"
    cfg.numbers_small_as_words = True
    app._apply_cleanup_settings(cfg)
    assert app._numbers_mode == "small_as_words"
    cfg.numbers_as_digits = False
    app._apply_cleanup_settings(cfg)
    assert app._numbers_mode is None


def test_preferences_has_the_tickbox_with_its_choices_beneath():
    from tuxtalk.prefs import PreferencesWindow
    changes = []

    class Stub:
        config = {"numbers_as_digits": False, "numbers_small_as_words": True}

        def update_config(self, key, value):
            changes.append((key, value))

    box = PreferencesWindow._numbers_option(Stub())
    check, choices = box.get_children()
    every, small = choices.get_children()
    assert "digits" in check.get_label() and check.get_active() is False
    assert small.get_active() is True and every.get_active() is False
    assert choices.get_margin_start() > 0          # indented under the tickbox
    assert choices.get_sensitive() is False        # greyed while the tickbox is off
    check.set_active(True)
    assert choices.get_sensitive() is True
    every.set_active(True)
    assert changes == [("numbers_as_digits", True), ("numbers_small_as_words", False)]

"""Whisper invents phrases during silence; stripping them must not eat real words.

The YouTube list is stripped from the end of *any* transcription, on the
grounds that nobody dictates "thanks for watching". That reasoning holds for
multi-word sign-offs. It does not hold for a bare verb.
"""

from talktype.app import _strip_hallucinations


# --- ordinary sentences must survive ---------------------------------------

def test_a_sentence_ending_in_subscribe_keeps_the_word():
    """"subscribe" was in the always-strip list, so any dictation ending in
    it silently lost the word — with no indication anything was removed."""
    assert _strip_hallucinations("tell them to subscribe", 0.0) == "tell them to subscribe"


def test_asking_someone_to_subscribe_survives():
    assert _strip_hallucinations("remind me to subscribe", 0.0) == "remind me to subscribe"


def test_subscribe_mid_sentence_survives():
    text = "the subscribe button is broken"
    assert _strip_hallucinations(text, 0.0) == text


# --- genuine YouTube outros are still stripped ------------------------------

def test_like_and_subscribe_is_still_stripped():
    out = _strip_hallucinations("here is my point like and subscribe", 0.0)
    assert "subscribe" not in out
    assert out.strip() == "here is my point"


def test_please_subscribe_is_still_stripped():
    out = _strip_hallucinations("here is my point please subscribe", 0.0)
    assert out.strip() == "here is my point"


def test_dont_forget_to_subscribe_is_still_stripped():
    out = _strip_hallucinations("here is my point don't forget to subscribe", 0.0)
    assert out.strip() == "here is my point"


def test_thanks_for_watching_is_still_stripped():
    out = _strip_hallucinations("that is the demo thanks for watching", 0.0)
    assert out.strip() == "that is the demo"


# --- the whole-text and trailing tiers are unchanged ------------------------

def test_a_silent_recording_transcribed_as_thank_you_is_dropped():
    assert _strip_hallucinations("thank you", 0.9).strip() == ""


def test_a_deliberate_thank_you_is_kept():
    """Low no_speech_prob means Whisper heard real speech."""
    assert _strip_hallucinations("thank you", 0.0).strip() == "thank you"

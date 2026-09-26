"""
Dictation cleanup: remove "um"/"uh" and accidental repeated words.

Deterministic rules, no AI and no download: instant, and it can only ever
delete hesitation sounds and exact repeats, never change a word you meant.
Self-corrections ("3, no wait, 4") need to understand the sentence, so those
are handled separately by the optional AI step (ai_cleanup.py).

Runs on the normalized text, after spoken commands have been turned into
punctuation, so an intentional "new line new line" (two line breaks) has
already become markers and is never mistaken for a stutter.
"""
import re

# Hesitation sounds. Deliberately narrow: "hmm" is often meant ("Hmm, not
# sure"), "er" is too close to real text, and "you know"/"like" depend on
# meaning, so none of those are touched.
_FILLER = r"(?:u+m+|u+h+m*|erm)"

# Words that are correctly doubled in ordinary English: "I know that that is
# true", "she had had enough", "what it is is...", "very very", "so so".
_LEGIT_DOUBLES = {"that", "had", "is", "do", "very", "so", "bye", "no", "yeah", "ha", "really", "far", "long"}

# Words that keep their own comma when a filler after them is removed.
_COMMA_WORDS = {"okay", "ok", "yes", "yeah", "no", "well", "so", "alright", "right",
                "sure", "oh", "hey", "hi", "hello", "thanks", "now", "anyway", "also"}

# A filler with the commas and spaces around it:  ", um,"  "Um, "  " uh "
_RE_FILLER = re.compile(rf"(?i)(,\s*)?\b{_FILLER}\b[,.]?\s*")

# One to three words repeated immediately with only spaces between them:
# "the the", "will will", "I think I think". A comma between the copies
# ("no, no, no", "again, again") usually means the repeat was deliberate.
_RE_REPEAT = re.compile(r"(?i)\b((?:[\w']+[ \t]+){0,2}[\w']+)(?:[ \t]+\1\b)+")


def _remove_fillers(text: str) -> str:
    def repl(m):
        start = m.start()
        at_line_start = start == 0 or text[:start].endswith(("\xa7", "\n"))
        # "Um, so we..." -> "So we...": when the filler opened a sentence (it
        # was capitalized), the word that now opens it takes the capital.
        capitalize = m.group(0).lstrip(", ")[:1].isupper()
        # ", uh," inside a sentence: both commas were only there for the
        # filler ("we should, uh, go" -> "we should go"). But after a word
        # like "okay" or "yes" the first comma is real punctuation:
        # "Okay, um, sounds good" -> "Okay, sounds good".
        prev = re.search(r"([\w']+)\W*$", text[:start])
        # A comma before the filler with none after it ("selected, um what")
        # was the sentence's own comma, so it stays too.
        trailing_comma = m.group(0).rstrip().endswith(",")
        keep_comma = bool(m.group(1)) and (
            not trailing_comma or (prev and prev.group(1).lower() in _COMMA_WORDS))
        sep = ", " if keep_comma else ("" if at_line_start else " ")
        return sep + ("\x00" if capitalize else "")
    out = _RE_FILLER.sub(repl, text)
    # \x00 marks "capitalize the next letter"; resolve it now.
    out = re.sub(r"\x00\s*(\w)", lambda m: m.group(1).upper(), out)
    return out.replace("\x00", "")


def _collapse_repeats(text: str) -> str:
    def repl(m):
        phrase = m.group(1)
        if phrase.lower() in _LEGIT_DOUBLES:
            return m.group(0)
        return phrase
    return _RE_REPEAT.sub(repl, text)


def _tidy(text: str, original: str) -> str:
    """Fix the spacing, punctuation and capitals the deletions left behind."""
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)          # "word ," -> "word,"
    text = re.sub(r",(\s*[,.!?;:])", r"\1", text)         # ",." or ",," -> "."
    text = re.sub(r"^[\s,]+", "", text)                    # leading comma/space
    # Keep the original's trailing space (auto-space adds one).
    if original.endswith(" ") and not text.endswith(" "):
        text += " "
    return text


def clean_fillers_and_repeats(text: str) -> str:
    """Remove "um"/"uh" and accidental repeated words from dictated text."""
    if not text:
        return text
    cleaned = _collapse_repeats(_remove_fillers(text))
    # A filler between two copies of a word ("the um the") becomes a repeat
    # only after the filler is gone, so collapse once more.
    cleaned = _collapse_repeats(cleaned)
    return _tidy(cleaned, text)

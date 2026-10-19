"""Write numbers as digits: "twenty-five chickens" becomes "25 chickens".

Parakeet writes small numbers, dates and ordinals as words ("three cats",
"october fifteenth"), while Whisper mostly writes digits, so the option
(Preferences → Advanced → Numbers) runs on the finished text and
works the same with every engine (GitHub Discussion #11).

The conversion itself is text2num's alpha2digit, which knows eight languages
and already leaves "no one", "one of them" and "the second one" alone. Around
it sit a few fixes for what it gets wrong in dictation:
- fractions stay words ("two thirds", not "two 3rds");
- "a hundred people" stays as said (not "a 100 people");
- digits read out one at a time join up ("08 6 2 0" -> "08620");
- years join up ("19 84" -> "1984", "19 oh 5" -> "1905");
- times get their colon ("at 7 30" -> "at 7:30").
The English-only fixes run for English alone; the rest is plain digits.
"""
import logging
import re

from .normalize import format_times

logger = logging.getLogger(__name__)

# The languages text2num reads.
SUPPORTED_LANGUAGES = frozenset({"en", "de", "es", "fr", "it", "pt", "nl", "da"})

# A lone number below this stays a word: text2num's own default (3) keeps "one"
# and "two", which are far more often words ("one of them", "two-way") than
# counts. Spelling out one to nine is the style-guide choice.
_ALL_THRESHOLD = 3
_SMALL_AS_WORDS_THRESHOLD = 10

_NUMBER_WORD = (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|"
                r"eleven|twelve|a|an)")
_FRACTION_WORD = r"(?:third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|quarter)"

# English phrases that must reach the reader as words, hidden from text2num:
# "two thirds", "three quarters", "a third of it", "one fifth".
_RE_FRACTION = re.compile(
    rf"\b(?:{_NUMBER_WORD}[\s-]+)?{_FRACTION_WORD}s\b"          # plural: always a fraction
    rf"|\b(?:a|one)[\s-]+{_FRACTION_WORD}\b(?=\s+of\b)"          # "a third of", "one fifth of"
    rf"|\bone[\s-]+{_FRACTION_WORD}\b",                          # "one third" on its own
    re.IGNORECASE,
)
# "a hundred people", unless more of the number follows ("a hundred and fifty").
_RE_A_HUNDRED = re.compile(
    r"\ban?\s+(?:hundred|thousand|million|billion)\b"
    r"(?!\s+(?:and\s+)?(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
    r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand)\b)",
    re.IGNORECASE,
)

# Three or more digits read out one at a time: a zip code, a PIN, a phone
# number. text2num gives "08 6 2 0" for "zero eight six two zero".
_RE_DIGIT_RUN = re.compile(r"(?<![\d.,:])\b(?:0\d|\d)(?: \d\b){2,}(?![.,:]?\d)")
# "at 7 30", "by 11 45": an hour of 1-12 and its minutes after a time word.
_RE_TIME_AFTER_WORD = re.compile(
    r"\b(at|by|until|till|from|before|after|around|about|to)\s+(1[0-2]|[1-9]) ([0-5]\d)\b",
    re.IGNORECASE,
)
# "7 15 pm": an hour and minutes right before am/pm.
_RE_TIME_BEFORE_AMPM = re.compile(
    r"\b(1[0-2]|[1-9]) ([0-5]\d)(?=\s*[ap]\.?\s*m\b\.?)", re.IGNORECASE)
# "19 84", "20 25": the two halves of a spoken year. Only centuries people
# actually say (1100s to 2000s), so "10 30" or "7 30" are never years.
_RE_YEAR = re.compile(r"(?<![\d.,:])\b(1[1-9]|20) ([1-9]\d)\b(?![.,:]?\d)")
# "19 oh 5": nineteen oh five.
_RE_YEAR_OH = re.compile(r"\b(1[1-9]|20) oh (\d)\b", re.IGNORECASE)


def _language(code: str) -> str:
    """"en_US", "pt-BR" or "de" -> the bare language code."""
    return (code or "").replace("-", "_").split("_")[0].lower()


def to_digits(text: str, language: str, small_as_words: bool = False) -> str:
    """*text* with its spoken numbers written as digits.

    *language* is the dictation language ("en", "de_CH", ...); for one
    text2num doesn't read, the text comes back unchanged. With
    *small_as_words*, a lone number below 10 stays a word ("three cats",
    "25 chickens"); digits read out one at a time are joined either way.
    """
    lang = _language(language)
    if not text or lang not in SUPPORTED_LANGUAGES:
        return text
    try:
        from text_to_num import alpha2digit
    except ImportError:
        logger.warning("Numbers as digits is on, but text2num isn't installed")
        return text

    english = lang == "en"
    # Hide the phrases that must stay words behind private-use characters,
    # which text2num reads as ordinary non-number words.
    hidden: list[str] = []

    def hide(m: re.Match) -> str:
        hidden.append(m.group())
        return chr(0xE000 + len(hidden) - 1)

    if english:
        text = _RE_FRACTION.sub(hide, text)
        text = _RE_A_HUNDRED.sub(hide, text)

    threshold = _SMALL_AS_WORDS_THRESHOLD if small_as_words else _ALL_THRESHOLD
    try:
        text = alpha2digit(text, lang, threshold=threshold)
    except Exception as e:  # a parser surprise must never cost the dictation
        logger.warning(f"Couldn't convert numbers to digits: {e}")

    if english:
        text = _RE_TIME_AFTER_WORD.sub(lambda m: f"{m.group(1)} {m.group(2)}:{m.group(3)}", text)
        text = _RE_TIME_BEFORE_AMPM.sub(lambda m: f"{m.group(1)}:{m.group(2)}", text)
        text = format_times(text)
        text = _RE_YEAR_OH.sub(lambda m: f"{m.group(1)}0{m.group(2)}", text)
    text = _RE_YEAR.sub(lambda m: m.group(1) + m.group(2), text)
    text = _RE_DIGIT_RUN.sub(lambda m: m.group().replace(" ", ""), text)

    for i, phrase in enumerate(hidden):
        text = text.replace(chr(0xE000 + i), phrase)
    return text

"""
Teach TalkType a word it keeps getting wrong, from a recent dictation.

The user picks the misheard words in a dictation ("bamboo studio") and types
what they should be ("BambuStudio"). The fix is saved as an ordinary custom
voice command, so:

- it works for every engine. It rewrites the transcription after the model
  heard it; Parakeet has no way to be told about words beforehand.
- it shows up (and can be edited or removed) in Preferences > Voice Commands.
- the dictation service picks it up on the next dictation, because it
  reloads custom_commands.toml whenever the file changes.

The dialog lives in fix_word_dialog.py; this module is the part with no GTK,
so the rules can be tested.
"""
import re

from . import config

_WORD_RE = re.compile(r"\S+")
# Punctuation hugging the ends of a selection: quotes, commas, full stops,
# brackets. Apostrophes inside a word ("it's") are not at an edge and stay.
_EDGE_RE = re.compile(r"^([^\w]*)(.*?)([^\w]*)$", re.DOTALL)

# Single words so common that "always fix" them would rewrite ordinary
# speech everywhere. Not exhaustive; it only has to catch the likely
# accidents, and the user can still go ahead after the warning.
_COMMON_WORDS = frozenset("""
a about after all also am an and any are as at be because been but by can
could did do does for from get go going got had has have he her here him his
how i if in into is it its it's just know like me more my no not now of on
one only or our out over really said say see she so some that the their them
then there these they this to too two three four five six seven eight nine ten
up us very was we well were what when where which who why will with would yes
yeah you your okay ok right
""".split())


def words(text):
    """The dictation split into the clickable words the dialog shows."""
    return _WORD_RE.findall(text)


def _selection(text, first, last):
    """(start, end) character span covering words *first*..*last* inclusive."""
    first, last = sorted((first, last))
    spans = [m.span() for m in _WORD_RE.finditer(text)]
    return spans[first][0], spans[last][1]


def word_span(text, first, last):
    """(start, end) character offsets covering words *first*..*last*, for
    highlighting the picked words in the dialog's text box."""
    return _selection(text, first, last)


def word_range(text, start, end):
    """The (first, last) words touched by a click or drag from *start* to
    *end* (character offsets, either order), or None if it hit only spaces.

    A plain click (start == end) picks the word under it, including a click
    just before its first letter or just after its last.
    """
    start, end = sorted((start, end))
    hit = []
    for i, m in enumerate(_WORD_RE.finditer(text)):
        if start == end:
            touched = m.start() <= start <= m.end()
        else:
            touched = m.start() < end and start < m.end()
        if touched:
            hit.append(i)
    return (hit[0], hit[-1]) if hit else None


def phrase_for(text, first, last):
    """The trigger phrase for a selection: lowercased, single-spaced, with the
    punctuation at its ends removed. Custom commands match case-insensitively
    against the raw transcription, which has no such punctuation."""
    start, end = _selection(text, first, last)
    core = _EDGE_RE.match(text[start:end]).group(2)
    return " ".join(core.split()).lower()


def fixed_text(text, first, last, replacement):
    """*text* with the selected words replaced, keeping the punctuation around
    them ("Bamboo Studio," -> "BambuStudio,") and everything else as it was."""
    start, end = _selection(text, first, last)
    lead, _core, trail = _EDGE_RE.match(text[start:end]).groups()
    return text[:start] + lead + replacement + trail + text[end:]


def is_risky(phrase):
    """True for a single everyday word, which would be rewritten every time
    the user says it, not just when the model mishears something."""
    return " " not in phrase and phrase in _COMMON_WORDS


def _matching_keys(commands, phrase):
    # Preferences stores phrases lowercased, but a hand-edited file may not.
    return [k for k in commands if " ".join(k.split()).lower() == phrase]


def existing_fix(phrase):
    """What *phrase* is already corrected to, or None."""
    commands = config.load_custom_commands()
    keys = _matching_keys(commands, phrase)
    return commands[keys[0]] if keys else None


def save_fix(phrase, replacement):
    """Save *phrase* -> *replacement* into the custom voice commands.

    Returns what the phrase used to be replaced with, or None if it is new.
    Raises config.ConfigNotLoadedError rather than write, if the existing
    commands file could not be read (writing would delete the user's commands).
    """
    commands = config.load_custom_commands()
    keys = _matching_keys(commands, phrase)
    previous = commands[keys[0]] if keys else None
    for k in keys:
        del commands[k]
    commands[phrase] = replacement
    config.save_custom_commands(commands)
    return previous

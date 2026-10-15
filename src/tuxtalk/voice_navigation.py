"""Select and move by voice (TuxTalk Labs): "select the last sentence",
"go to the end", "unselect".

Pure logic, like undo.py: which dictations are commands, and the keys each
one presses. app.py presses them through the output backend, so the host
(ydotool) and the Flatpak (libei) do the same.

A dictation is a command only when the WHOLE of it is one of the phrases
here, so "I want to select the last sentence" is typed as text. Plain F8
never rewrites anything: rewording stays on the voice-edit key. See
docs/superpowers/specs/2026-10-14-select-and-move-by-voice-design.md.

Keys are named, not numbered ("CTRL", "LEFT", "A"); the backend turns them
into key codes, the letter A for the active keyboard layout.
"""
import re
from dataclasses import dataclass

from .undo import calculate_undo_length

C, S = "CTRL", "SHIFT"
MAX_COUNT = 10

_NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                 "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_N = r"(?:(?P<n>\d+|" + "|".join(_NUMBER_WORDS) + r")\s+)?"


@dataclass(frozen=True)
class Command:
    name: str               # for the log: "go back 3 words"
    said_unit: str = ""     # "all", "word", "sentence" or "paragraph": what I just said
    count: int = 1
    keys: tuple = ()        # pressed count times
    first: tuple = ()       # pressed once before (Home, for "select the line")


def _norm(text: str) -> str:
    """Lower case, letters, digits and single spaces; no "please"."""
    s = re.sub(r"[^\w\s']", " ", (text or "").lower())
    s = " ".join(s.split())
    s = re.sub(r"^please\s+|\s+please$", "", s)
    return s


# (pattern, builder). Each pattern matches the whole normalized dictation; the
# builder gets the count and returns (said_unit, keys, first).
_DOC = r"(?:\s+of\s+(?:the\s+)?(?:document|page|text))?"
_RULES = [
    # What I just said: exact, from the text TuxTalk typed last.
    (r"select (?:that|it|what i (?:just )?said|the last dictation)", lambda n: ("all", (), ())),
    (rf"select (?:the )?last {_N}(?P<u>word|sentence|paragraph)s?", lambda n, u: (u, (), ())),
    # Around the cursor.
    (r"select (?:all|everything)", lambda n: ("", (((C,), "A"),), ())),
    (r"select (?:the|this) line", lambda n: ("", (((S,), "END"),), (((), "HOME"),))),
    (rf"select (?:the )?next {_N}words?", lambda n: ("", (((C, S), "RIGHT"),), ())),
    (rf"select (?:the )?previous {_N}words?", lambda n: ("", (((C, S), "LEFT"),), ())),
    (rf"select (?:the )?next {_N}lines?", lambda n: ("", (((S,), "DOWN"),), ())),
    (rf"select (?:the )?previous {_N}lines?", lambda n: ("", (((S,), "UP"),), ())),
    (r"select to (?:the )?end of (?:the )?line", lambda n: ("", (((S,), "END"),), ())),
    (r"select to (?:the )?(?:start|beginning) of (?:the )?line", lambda n: ("", (((S,), "HOME"),), ())),
    (rf"select to (?:the )?(?:end|bottom){_DOC}", lambda n: ("", (((C, S), "END"),), ())),
    (rf"select to (?:the )?(?:start|beginning|top){_DOC}", lambda n: ("", (((C, S), "HOME"),), ())),
    # Moving.
    (r"go to (?:the )?end of (?:the )?line", lambda n: ("", (((), "END"),), ())),
    (r"go to (?:the )?(?:start|beginning) of (?:the )?line", lambda n: ("", (((), "HOME"),), ())),
    (rf"go to (?:the )?(?:end|bottom){_DOC}", lambda n: ("", (((C,), "END"),), ())),
    (rf"go to (?:the )?(?:start|beginning|top){_DOC}", lambda n: ("", (((C,), "HOME"),), ())),
    (rf"go (?:back|left) {_N}words?|previous word", lambda n: ("", (((C,), "LEFT"),), ())),
    (rf"go (?:forward|right) {_N}words?|next word", lambda n: ("", (((C,), "RIGHT"),), ())),
    (rf"go (?:back|left) {_N}(?:characters?|letters?)", lambda n: ("", (((), "LEFT"),), ())),
    (rf"go (?:forward|right) {_N}(?:characters?|letters?)", lambda n: ("", (((), "RIGHT"),), ())),
    (rf"go up {_N}lines?", lambda n: ("", (((), "UP"),), ())),
    (rf"go down {_N}lines?", lambda n: ("", (((), "DOWN"),), ())),
    # Unselect: Right collapses a selection to its end.
    (r"(?:unselect|deselect)(?: (?:that|it|all|everything))?|clear (?:the )?selection",
     lambda n: ("", (((), "RIGHT"),), ())),
]
_COMPILED = [(re.compile(rf"^(?:{pattern})$"), build) for pattern, build in _RULES]


def parse(text: str):
    """The Command *text* is, or None when it's dictation to type."""
    said = _norm(text)
    if not said:
        return None
    for pattern, build in _COMPILED:
        m = pattern.fullmatch(said)
        if not m:
            continue
        groups = m.groupdict()
        raw = groups.get("n")
        count = 1 if raw is None else (int(raw) if raw.isdigit() else _NUMBER_WORDS[raw])
        if not 1 <= count <= MAX_COUNT:
            return None
        args = (count, groups["u"]) if "u" in groups and groups["u"] else (count,)
        unit, keys, first = build(*args)
        name = said if raw is None else said[:m.start("n")] + str(count) + said[m.end("n"):]
        return Command(name=name, said_unit=unit, count=count, keys=keys, first=first)
    return None


def needs_last_text(command: Command) -> bool:
    """Whether *command* works on what TuxTalk typed last."""
    return bool(command.said_unit)


def chords(command: Command, last_text: str):
    """The keys to press, in order, as [(modifiers, key)]; None when the
    command needs the last dictation and there is none."""
    if not command.said_unit:
        return list(command.first) + list(command.keys) * command.count
    if not last_text or not last_text.strip():
        return None
    if command.said_unit == "all":
        span = last_text
    else:
        span = last_text[-calculate_undo_length(last_text, command.said_unit, command.count):]
    # The cursor sits after the span: step over its trailing spaces without
    # selecting them, then select back over the words. Its leading space (auto-
    # space before a dictation) stays out of the selection.
    trailing = len(span) - len(span.rstrip())
    words = len(span.strip())
    return [((), "LEFT")] * trailing + [((S,), "LEFT")] * words

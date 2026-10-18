"""Saying "press enter" at the end of a dictation sends a real Enter.

"See you at noon, press enter" types "See you at noon." and then presses
Enter, so a chat message is sent, a terminal command runs or a form is
submitted, without touching the keyboard. "press enter" on its own just
presses Enter. A spoken "new line" stays Shift+Enter (normalize.py), which
starts a new line without sending anything.

Only the very end of a dictation counts, so "press enter to continue" in the
middle of a sentence is typed as words. Saying "literal press enter" types
the words too.

"Send each dictation automatically" presses Enter without being asked, so it
holds back when the dictation was plainly cut off ("... and I think and"):
sending half a sentence can't be taken back (ends_unfinished).
"""

import re

# "press enter", "hit enter", "press the enter key", "press return".
# Speech engines often capitalise and punctuate it ("... noon. Press Enter.").
_TRAILING = re.compile(
    r"(?P<lead>^|[\s,;:.!?]+)"
    r"(?P<literal>literal\s+)?"
    r"(?:press|hit)\s+(?:the\s+)?(?:enter|return)(?:\s+key)?"
    r"[\s.!?,]*$",
    re.IGNORECASE,
)


def split_press_enter(raw: str) -> tuple[str, bool]:
    """(the dictation without a closing "press enter", whether it was said).

    The words before it keep their own sentence-ending punctuation ("noon."),
    but a comma or colon that only led into the command is dropped.
    """
    if not raw:
        return raw, False
    match = _TRAILING.search(raw)
    if not match:
        return raw, False
    if match.group("literal"):
        # Typed as words, without "literal", like "literal new line".
        return raw[:match.start("literal")] + raw[match.end("literal"):], False
    rest = raw[:match.start()]
    # Keep "." "?" "!" from the lead-in (it ended the sentence), not "," ";" ":".
    lead = match.group("lead").strip()
    ending = next((c for c in lead if c in ".!?"), "")
    rest = rest.rstrip(" ,;:") + ending
    return rest.strip(), True


# Words an English sentence doesn't end on: letting go of the key after one
# means the dictation was cut off. Kept short on purpose. "so", "to", "that"
# and "then" are left out because "I think so", "I'd love to", "I like that"
# and "see you then" are whole sentences.
_UNFINISHED = frozenset({
    "and", "but", "or", "because", "the", "a", "an", "of", "with", "if",
    "my", "your", "our", "their", "um", "uh",
})


def ends_unfinished(text: str) -> str:
    """The word a cut-off dictation ends on ("and"), or "" when it looks whole."""
    words = text.split()
    if not words:
        return ""
    last = words[-1].strip(".,;:!?\"'\u201c\u201d\u2018\u2019").lower()
    return last if last in _UNFINISHED else ""

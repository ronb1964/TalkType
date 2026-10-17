"""Saying "press enter" at the end of a dictation sends a real Enter.

"See you at noon, press enter" types "See you at noon." and then presses
Enter, so a chat message is sent, a terminal command runs or a form is
submitted, without touching the keyboard. "press enter" on its own just
presses Enter. A spoken "new line" stays Shift+Enter (normalize.py), which
starts a new line without sending anything.

Only the very end of a dictation counts, so "press enter to continue" in the
middle of a sentence is typed as words. Saying "literal press enter" types
the words too.
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

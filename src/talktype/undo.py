"""
Undo voice-command parsing and character-length calculation.

Pure logic — no ydotool, GTK, or audio dependencies. Importable from tests
without dragging in CUDA/Whisper/etc. The keystroke-sending side
(`_send_backspaces`, `_send_select_all_delete`) lives in app.py.
"""

import re

# "Everything" phrases clear the entire input field (Ctrl+A + Backspace) and
# don't require any tracked dictation. Exact-match strings.
EVERYTHING_PATTERNS = frozenset({
    'undo everything', 'undo all',
    'delete everything', 'delete all',
    'clear everything', 'clear all',
})

# Spoken number words → integers. Used for counted undo like
# "delete last three sentences". "a"/"an" map to 1 because Whisper often
# transcribes "delete a sentence" instead of "delete one sentence".
NUMBER_WORDS = {
    'a': 1, 'an': 1,
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
}

# Counted/uncounted unit-undo regex. Matches:
#   "delete last word"            → ('word', 1)
#   "undo last two sentences"     → ('sentence', 2)
#   "remove last 3 paragraphs"    → ('paragraph', 3)
#   "delete the last five words"  → ('word', 5)
_UNDO_UNIT_RE = re.compile(
    r"^(?:undo|delete|remove)\s+(?:the\s+)?last\s+"
    r"(?:(\d+)\s+|(" + "|".join(re.escape(w) for w in NUMBER_WORDS) + r")\s+)?"
    r"(word|sentence|paragraph)s?$",
    re.IGNORECASE,
)


def detect_undo_command(raw_text: str) -> tuple[str, int] | None:
    """
    Check if the raw transcription is an undo command.

    Returns a (undo_type, count) tuple or None.
    - undo_type: 'word', 'sentence', 'paragraph', or 'everything'
    - count: how many units to remove (always 1 for 'everything')
    """
    normalized = re.sub(r'[^\w\s]', '', raw_text.lower()).strip()
    normalized = ' '.join(normalized.split())

    if normalized in EVERYTHING_PATTERNS:
        return ('everything', 1)

    m = _UNDO_UNIT_RE.match(normalized)
    if m:
        digit, word, unit = m.groups()
        if digit:
            count = int(digit)
        elif word:
            count = NUMBER_WORDS[word.lower()]
        else:
            count = 1
        return (unit.lower(), count)

    return None


def single_unit_length(text: str, undo_type: str) -> int:
    """
    Length (in characters) of the LAST word/sentence/paragraph in `text`.

    Returns len(text) when no internal boundary is found (i.e. the whole
    remaining buffer is the last unit). The 'everything' type is handled
    by the caller — it's not a per-unit measurement.
    """
    if not text:
        return 0

    text_to_analyze = text.rstrip()

    if undo_type == 'word':
        last_space = text_to_analyze.rfind(' ')
        if last_space == -1:
            return len(text)
        return len(text) - last_space - 1

    if undo_type == 'sentence':
        # Skip any trailing sentence-ending punctuation so we find the
        # PREVIOUS sentence end, not the current one.
        text_stripped = text_to_analyze.rstrip('.?!… ')
        match = re.search(r'[.?!…]\s*', text_stripped[::-1])
        if match:
            pos = len(text_stripped) - match.start()
            return len(text) - pos
        return len(text)

    if undo_type == 'paragraph':
        marker = "§SHIFT_ENTER§"
        marker_pos = text_to_analyze.rfind(marker)
        newline_pos = text_to_analyze.rfind('\n')
        if marker_pos > newline_pos:
            return len(text) - marker_pos - len(marker)
        if newline_pos != -1:
            return len(text) - newline_pos - 1
        return len(text)

    return 0


def calculate_undo_length(text: str, undo_type: str, count: int = 1) -> int:
    """
    Calculate how many characters to delete based on undo type and count.

    For counted undos ("delete last 3 sentences"), iterates the single-unit
    logic N times, accumulating the cut length. Clamps to what's available —
    "delete last 50 words" on a 3-word buffer just removes those 3 words.

    Args:
        text: The last inserted text
        undo_type: 'word', 'sentence', 'paragraph', or 'everything'
        count: how many units to remove (ignored for 'everything')

    Returns:
        Number of characters to delete (backspaces to send)
    """
    if not text or count < 1:
        return 0

    if undo_type == 'everything':
        return len(text)

    total = 0
    remaining = text
    completed = 0
    while completed < count and remaining:
        single = single_unit_length(remaining, undo_type)
        if single > 0:
            total += single
            remaining = remaining[:len(remaining) - single]
            completed += 1
            continue
        # single == 0 means we're sitting right at a paragraph boundary
        # (single_unit_length for 'paragraph' subtracts the marker length,
        # so when the marker is at the very end, it returns 0). Step past
        # the trailing marker/newline so the next iteration can find the
        # previous paragraph instead of looping on the same position.
        if undo_type == 'paragraph':
            marker = "§SHIFT_ENTER§"
            if remaining.endswith(marker):
                total += len(marker)
                remaining = remaining[:-len(marker)]
                continue
            if remaining.endswith('\n'):
                total += 1
                remaining = remaining[:-1]
                continue
        break
    return total

import re

# =====================================================================
# Precompiled regex patterns — compiled once at import time.
# This avoids recompiling 40+ patterns on every dictation call.
# =====================================================================

# --- 0) Quoted text protection ---
_RE_QUOTED_TEXT = re.compile(
    r'\b(?:open\s+quotes?)[,.\s]+(.*?)[,.\s]+(?:close\s+quotes?)\b',
    re.IGNORECASE
)

# --- 0.1) Literal word escapes ---
# Map of spoken words to placeholder tokens. When the user says
# "literal period" we preserve the word "period" instead of inserting "."
LITERAL_REPLACEMENTS = {
    "period": "__LIT_PERIOD__",
    "comma": "__LIT_COMMA__",
    "tab": "__LIT_TAB__",
    "newline": "__LIT_NEWLINE__",
    "new line": "__LIT_NEW_LINE__",
    "return": "__LIT_RETURN__",
    "line break": "__LIT_LINEBREAK__",
    "new paragraph": "__LIT_NEWPARA__",
    "paragraph break": "__LIT_PARABK__",
    "question mark": "__LIT_QMARK__",
    "exclamation point": "__LIT_EPOINT__",
    "exclamation mark": "__LIT_EPOINT2__",
    "semicolon": "__LIT_SEMICOLON__",
    "colon": "__LIT_COLON__",
    "apostrophe": "__LIT_APOSTROPHE__",
    "quote": "__LIT_QUOTE__",
    "hyphen": "__LIT_HYPHEN__",
    "dash": "__LIT_DASH__",
    "ellipsis": "__LIT_ELLIPSIS__",
    "dot dot dot": "__LIT_DOTDOTDOT__",
}

# Restore mapping: each placeholder → its original spoken word (1:1, lossless)
LITERAL_RESTORE = {ph: word for word, ph in LITERAL_REPLACEMENTS.items()}

# Precompile literal escape patterns: "literal <word>" or "the word <word>"
_LITERAL_PATTERNS = [
    (re.compile(rf"\b(?:literal|the\s+words?)\s+{re.escape(word)}\b", re.IGNORECASE), placeholder)
    for word, placeholder in LITERAL_REPLACEMENTS.items()
]

# --- 0.2) Context-aware protection for command words used as English nouns ---
# Words like "period", "comma", "return", "dash", "quote" are command triggers
# in dictation, but they are also normal English nouns in phrases like "period
# of time", "in return", "a dash of salt", "the comma operator". Without this
# pass, those phrases get corrupted: "period of time" → "period. Of time".
#
# Each pattern captures surrounding context and substitutes a placeholder for
# just the protected word. Same mechanism as _LITERAL_PATTERNS — placeholders
# are restored to their original words by the pass at step 12.
_CONTEXT_PROTECT_PATTERNS = [
    # "[article/adj/possessive] period" — strong noun signal
    (re.compile(
        r"\b(a|an|the|this|that|these|those|my|his|her|its|our|their|your|"
        r"any|some|each|every|long|short|brief|extended|lengthy|given|"
        r"certain|trial|grace|menstrual|test|same|full|half|specific|"
        r"particular|entire|whole|two-week|three-month|24-hour)\s+period\b",
        re.IGNORECASE,
    ), r"\1 __LIT_PERIOD__"),
    # "period of [word]" — fixed noun phrase: "period of time", "period of mourning"
    (re.compile(r"\bperiod(\s+of\b)", re.IGNORECASE), r"__LIT_PERIOD__\1"),

    # "[prep/article/possessive/adj/modal] return" — noun/verb usage.
    # Modals ("will/can return") and infinitive "to return" are always the
    # verb. Subject pronouns are deliberately NOT protected: "thank you
    # return" is a very common command usage and must keep working.
    (re.compile(
        r"\b(in|on|at|the|a|an|my|his|her|its|our|their|your|tax|safe|"
        r"swift|prompt|early|late|partial|full|complete|annual|monthly|"
        r"yearly|first|second|third|grand|major|sudden|big|home|no|any|"
        r"every|each|some|triumphant|long-awaited|"
        r"to|will|would|can|could|shall|should|may|might|must|never|not|"
        r"ll|just|please)\s+return\b",
        re.IGNORECASE,
    ), r"\1 __LIT_RETURN__"),
    # "return [to/of/from/home/...]" — verb or noun-of-X usage
    (re.compile(
        r"\breturn(\s+(?:to|of|from|home|the|on|by|policy|address|trip|"
        r"flight|ticket|date|window|policy|customer|item))\b",
        re.IGNORECASE,
    ), r"__LIT_RETURN__\1"),
    # "return it/this/that TO/FOR/..." — pronoun object plus a second signal
    # word. Bare "return this ..." is NOT protected: "this/it/a" are the most
    # common sentence starters after a line-break command.
    (re.compile(
        r"\breturn(\s+(?:it|this|that|them|these|those)\s+"
        r"(?:to|from|for|by|at|in|on|before|after|tomorrow|today|soon|"
        r"later|now|please|immediately))\b",
        re.IGNORECASE,
    ), r"__LIT_RETURN__\1"),

    # "[article/adj] tab" — browser/UI noun usage ("a new tab", "the wrong
    # tab"). Ordinals are deliberately NOT protected: "first tab second tab
    # third" is tab-as-field-separator dictation and must keep working.
    (re.compile(
        r"\b(a|an|the|this|that|these|those|my|his|her|its|our|their|your|"
        r"new|another|current|wrong|right|same|other|browser|chrome|firefox)\s+tab\b",
        re.IGNORECASE,
    ), r"\1 __LIT_TAB__"),
    # "tab [key/bar/...]" — noun compounds ("press tab key" is about the key name)
    (re.compile(
        r"\btab\s+(key|bar|stop|order|character|button|group|title)\b",
        re.IGNORECASE,
    ), r"__LIT_TAB__ \1"),

    # "[article/adj] dash"
    (re.compile(
        r"\b(a|an|the|this|that|my|his|her|every|each|any|some|"
        r"quick|sudden|mad|small|tiny|little|big|huge)\s+dash\b",
        re.IGNORECASE,
    ), r"\1 __LIT_DASH__"),
    # "dash of [word]"
    (re.compile(r"\bdash(\s+of\b)", re.IGNORECASE), r"__LIT_DASH__\1"),

    # "[article/adj/possessive] quote"
    (re.compile(
        r"\b(a|an|the|this|that|my|his|her|its|our|their|your|every|each|"
        r"any|some|famous|great|good|nice|important|brief|long|short|"
        r"memorable|favorite|powerful|funny|inspiring)\s+quote\b",
        re.IGNORECASE,
    ), r"\1 __LIT_QUOTE__"),

    # "comma operator/splice/key" — programming / writing terminology
    (re.compile(r"\bcomma\s+(operator|splice|key)\b", re.IGNORECASE),
     r"__LIT_COMMA__ \1"),
    # "Oxford/serial comma" — writing style
    (re.compile(r"\b(oxford|serial)\s+comma\b", re.IGNORECASE),
     r"\1 __LIT_COMMA__"),
]

# --- 1) Multi-word spoken punctuation → symbol ---
_MULTI_WORD_REPLACEMENTS = [
    (re.compile(r"\s*\bnew\s*line\b[,.\s]*|\bnewline\b|\breturn\b|\bline\s+break\b", re.IGNORECASE), "§SHIFT_ENTER§"),
    (re.compile(r"[,.\s]*\bnew\s+paragraph\b[,.\s]*|\bparagraph\s+break\b[,.\s]*", re.IGNORECASE), "§SHIFT_ENTER§§SHIFT_ENTER§"),
    (re.compile(r"[,.\s]*\bsoft\s+break\b[,.\s]*|\bsoft\s+line\b[,.\s]*", re.IGNORECASE), "   "),
    (re.compile(r"\btab\b", re.IGNORECASE), "\t"),
    (re.compile(r"\bexclamation\s+point\b|\bexclamation\s+mark\b", re.IGNORECASE), "!"),
    (re.compile(r"\bquestion\s+mark\b", re.IGNORECASE), "?"),
    (re.compile(r"\bfull\s*stop\b", re.IGNORECASE), "."),
    (re.compile(r"\bdot\s+dot\s+dot\b|\bellipsis\b", re.IGNORECASE), "…"),
    (re.compile(r"\bopen\s+parenthesis\b", re.IGNORECASE), "("),
    (re.compile(r"\bclose\s+parenthesis\b", re.IGNORECASE), ")"),
    (re.compile(r"\bopen\s+bracket\b", re.IGNORECASE), "["),
    (re.compile(r"\bclose\s+bracket\b", re.IGNORECASE), "]"),
    (re.compile(r"\bopen\s+brace\b", re.IGNORECASE), "{"),
    (re.compile(r"\bclose\s+brace\b", re.IGNORECASE), "}"),
    (re.compile(r"\bopen\s+quote\b|\bopen\s+quotes\b", re.IGNORECASE), "\u201c"),
    (re.compile(r"\bclose\s+quote\b|\bclose\s+quotes\b", re.IGNORECASE), "\u201d"),
]

# --- 2) Single-word spoken punctuation → symbol ---
_SINGLE_WORD_REPLACEMENTS = [
    (re.compile(r"\bcomma\b,?", re.IGNORECASE), ","),
    (re.compile(r"\bsemicolon\b;?", re.IGNORECASE), ";"),
    (re.compile(r"\bcolon\b:?", re.IGNORECASE), ":"),
    (re.compile(r"\bperiod\b\.?", re.IGNORECASE), "."),
    (re.compile(r"\bapostrophe\b", re.IGNORECASE), "'"),
    (re.compile(r"\bquote\b", re.IGNORECASE), '"'),
    # "em dash" MUST run before the bare hyphen/dash rule — otherwise
    # "em dash" is rewritten to "em -" first and this pattern never matches.
    (re.compile(r"\bem\s*dash\b", re.IGNORECASE), "—"),
    (re.compile(r"\bhyphen\b|\bdash\b", re.IGNORECASE), "-"),
]

# --- 3) Quotes/brackets spacing ---
_RE_OPEN_BRACKET_SPACE = re.compile(r"(\(|\[|\{)\s+")
_RE_SPACE_CLOSE_BRACKET = re.compile(r"\s+(\)|\]|\})")
_RE_OPEN_SMART_QUOTE_SPACE = re.compile(r"(\u201c)\s+")
_RE_SPACE_CLOSE_SMART_QUOTE = re.compile(r"\s+(\u201d)")
_RE_OPEN_QUOTE_COMMA = re.compile(r"\u201c\s*,+")
_RE_COMMA_CLOSE_QUOTE = re.compile(r",+\s*\u201d")

# --- 4) Space before punctuation ---
_RE_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,;:.?!…—-])")

# --- 5) Normalize punctuation combos ---
_RE_WEAK_BEFORE_STRONG = re.compile(r"[,;:]\s*([.?!…])")
_RE_PERIOD_AFTER_BANG_Q = re.compile(r"([!?])\s*\.")
_RE_COMMA_AFTER_BANG_Q = re.compile(r"([!?])\s*,")
_RE_COMMAS_BEFORE_BANG_Q = re.compile(r",+\s*([!?])")
_RE_COMMA_BEFORE_PERIOD = re.compile(r",\s*\.")
_RE_MULTIPLE_COMMAS = re.compile(r",\s*,+")
_RE_DASH_COLON = re.compile(r"-\s*:")
_RE_COLON_DASH = re.compile(r":\s*-")

# --- 6) Collapse punctuation runs ---
_RE_MANY_DOTS = re.compile(r"\.{4,}")
_RE_DOUBLE_DOT = re.compile(r"(?<!\.)\.\.(?!\.)")
_RE_REPEATED_BANG_Q = re.compile(r"([!?])\1+")

# --- 7) Space after sentence enders ---
_RE_SPACE_AFTER_ENDER = re.compile(r"([.?!…])(?!\s|$|[\u201d\)\]\}])")

# --- 8) Em dash / hyphen spacing ---
_RE_EM_DASH_SPACE = re.compile(r"\s*—\s*")
_RE_HYPHEN_SPACE = re.compile(r"\s*-\s*")

# --- 9) Tidy spaces around newlines ---
_RE_SPACE_BEFORE_NEWLINE = re.compile(r"[ \t]+\n")
_RE_SPACE_AFTER_NEWLINE = re.compile(r"\n[ ]+")
_RE_LEADING_PUNCT = re.compile(r"^[\s]*[\.,;:!?]+(?!…)")
_RE_MULTI_SPACE = re.compile(r"[ ]{2,}")

# --- 10) Capitalization ---
_RE_TRAILING_COMMA = re.compile(r",$")
_RE_NO_END_PUNCT = re.compile(r"[.?!…]$")
# Negative lookbehind: don't capitalize after single-letter abbreviations
# ("e.g. that" / "U.S. economy" must not become "e.g. That" / "U.S. Economy").
_RE_CAP_AFTER_ENDER = re.compile(r"(?<![A-Za-z]\.[A-Za-z])([.?!…]\s+)([a-z])")
# Standalone lowercase "i" → "I" (also catches "i'll", "i'm", "i've", "i'd"
# because the apostrophe is a word boundary). Case-sensitive: an existing
# "I" is left alone. Words like "in", "it", "iPad" are not matched because
# they have no word boundary on the right side of the "i".
_RE_STANDALONE_I = re.compile(r"\bi\b")

# --- 11) Smart quote punctuation placement ---
_RE_PUNCT_OUTSIDE_QUOTE = re.compile(r"\u201d( ?)([!?,;:.])")

# --- 14) Email/URL formatting ---
_RE_EMAIL_AT_WORD = re.compile(
    r"([a-zA-Z0-9._-]+)\s+at\s+([a-zA-Z0-9.-]+)\s*\.\s*"
    r"(com|org|net|edu|gov|io|co|uk|ca|de|fr|us|au|jp|cn|in|br|mx|ru|kr|es|it|nl|se|no|fi|pl|cz|hu|ro|gr|pt|ie|nz|za|ae|il|tr|th|vn|ph|id|my|sg|hk|tw)\b",
    re.IGNORECASE
)
_EMAIL_TLD_FIXES = [
    (re.compile(r"@\s+"), "@"),
    (re.compile(r"\.\s*([Cc]om)\b"), ".com"),
    (re.compile(r"\.\s*([Oo]rg)\b"), ".org"),
    (re.compile(r"\.\s*([Nn]et)\b"), ".net"),
    (re.compile(r"\.\s*([Ee]du)\b"), ".edu"),
    (re.compile(r"\.\s*([Gg]ov)\b"), ".gov"),
    (re.compile(r"\.\s*([Ii]o)\b"), ".io"),
    (re.compile(r"\.\s*([Cc]o)\b"), ".co"),
    (re.compile(r"\.\s*([Uu]k)\b"), ".uk"),
    (re.compile(r"\.\s*([Cc]a)\b"), ".ca"),
    (re.compile(r"\.\s*([Dd]e)\b"), ".de"),
    (re.compile(r"\.\s*([Ff]r)\b"), ".fr"),
]

# --- 15) Time formatting ---
# Fix Whisper's mangled time output: "11. 30 p. m." → "11:30 PM", "11 p. m." → "11 PM"
# Minutes are optional — handles both "11:30 p. m." and bare "11 p. m."
# AM/PM variants handled: "p. m.", "p. M.", "p.m.", "PM", "a. m.", "a.m.", "AM" (any case/spacing).
# The trailing (?![A-Za-z]) stops the AM/PM group from matching the start of
# ordinary words: "5 among us" / "3 amazing" are not times.
_RE_TIME_FORMAT = re.compile(
    r'\b(1[0-2]|0?[1-9])(?:[.:]\s*([0-5][0-9]))?\s+([Pp]\.?\s*[Mm]\.?|[Aa]\.?\s*[Mm]\.?)(?![A-Za-z])',
    re.IGNORECASE
)

def _fix_time_ampm(m: re.Match) -> str:
    """Normalize a matched time string to HH:MM AM/PM or HH AM/PM format."""
    hour = m.group(1)
    minute = m.group(2)  # None if no minutes were present
    ampm = re.sub(r'[\s.]', '', m.group(3)).upper()  # "p. m." / "p. M." → "PM"
    if minute:
        return f"{hour}:{minute} {ampm}"
    return f"{hour} {ampm}"


def _space_after_ender_repl(m: re.Match) -> str:
    """Insert a space after a sentence ender — except inside numbers and
    single-letter abbreviations, where the period is part of the token:
    '3.5', '$19.99', 'U.S.', 'e.g.', 'a.m.' must not be split apart."""
    ch = m.group(1)
    if ch == ".":
        s, i = m.string, m.start(1)
        prev = s[i - 1] if i > 0 else ""
        prev2 = s[i - 2] if i > 1 else ""
        nxt = s[i + 1] if i + 1 < len(s) else ""
        nxt2 = s[i + 2] if i + 2 < len(s) else ""
        # Decimal/price/version numbers: digit.digit
        if prev.isdigit() and nxt.isdigit():
            return ch
        # Single-letter abbreviations: e.g., i.e., U.S., a.m.
        # (single letter before the dot, letter+dot after it)
        if prev.isalpha() and not prev2.isalpha() and nxt.isalpha() and nxt2 == ".":
            return ch
    return ch + " "


# Trailing line-break markers (possibly repeated) at the end of an utterance.
_RE_TRAILING_BREAKS = re.compile(r"(?:\s*(?:§SHIFT_ENTER§))+\s*$")


def append_auto_punct(text: str, auto_period: bool, auto_space: bool) -> str:
    """Append the automatic period/space to a finished utterance.

    When the utterance ends with line-break markers ("hello new line"),
    the period must land BEFORE the break — appending it after produced
    an orphan ". " at the start of the next line. No trailing space is
    added after a line break (the cursor is already on a fresh line).
    """
    if not text:
        return text
    m = _RE_TRAILING_BREAKS.search(text)
    if m:
        core, trailing = text[:m.start()], text[m.start():]
        if not core.strip():
            return text  # utterance is only line breaks — nothing to punctuate
        if auto_period and not core.rstrip().endswith((".", "?", "!", "…")):
            core = core.rstrip() + "."
        return core + trailing
    if auto_period and not text.rstrip().endswith((".", "?", "!", "…")):
        text = text.rstrip() + "."
    if auto_space and not text.endswith((" ", "\n", "\t")):
        text = text + " "
    return text


# =====================================================================
# Main normalization function
# =====================================================================

def normalize_text(text: str) -> str:
    """Spoken punctuation -> symbols; tidy punctuation; auto-capitalize; keep newlines/tabs."""
    if not text:
        return text

    # --- 0) Handle quoted text - preserve everything inside quotes as literal ---
    quoted_sections = []
    def save_quoted(match):
        quoted_sections.append(match.group(1))
        return f"__QUOTED_{len(quoted_sections)-1}__"

    text = _RE_QUOTED_TEXT.sub(save_quoted, text)

    # --- 0.1) Escape sequences for literal words ---
    for pat, placeholder in _LITERAL_PATTERNS:
        text = pat.sub(placeholder, text)

    # --- 0.2) Protect command words used as English nouns ("period of time",
    #          "in return", "a dash of salt", "comma operator", etc.) ---
    for pat, repl in _CONTEXT_PROTECT_PATTERNS:
        text = pat.sub(repl, text)

    # --- 1) Multi-word replacements first (order matters) ---
    for pat, repl in _MULTI_WORD_REPLACEMENTS:
        text = pat.sub(repl, text)

    # --- 2) Single-word replacements ---
    for pat, repl in _SINGLE_WORD_REPLACEMENTS:
        text = pat.sub(repl, text)

    # --- 3) Quotes/brackets spacing ---
    text = _RE_OPEN_BRACKET_SPACE.sub(r"\1", text)
    text = _RE_SPACE_CLOSE_BRACKET.sub(r"\1", text)
    text = _RE_OPEN_SMART_QUOTE_SPACE.sub(r"\1", text)
    text = _RE_SPACE_CLOSE_SMART_QUOTE.sub(r"\1", text)
    text = _RE_OPEN_QUOTE_COMMA.sub("\u201c", text)
    text = _RE_COMMA_CLOSE_QUOTE.sub("\u201d", text)

    # --- 4) Remove spaces before punctuation ---
    text = _RE_SPACE_BEFORE_PUNCT.sub(r"\1", text)

    # --- 5) Normalize punctuation combos ---
    text = _RE_WEAK_BEFORE_STRONG.sub(r"\1", text)
    text = _RE_PERIOD_AFTER_BANG_Q.sub(r"\1", text)
    text = _RE_COMMA_AFTER_BANG_Q.sub(r"\1", text)
    text = _RE_COMMAS_BEFORE_BANG_Q.sub(r"\1", text)
    text = _RE_COMMA_BEFORE_PERIOD.sub(".", text)
    text = _RE_MULTIPLE_COMMAS.sub(",", text)
    text = _RE_DASH_COLON.sub(":", text)
    text = _RE_COLON_DASH.sub(":", text)

    # --- 6) Collapse punctuation runs; handle ellipsis ---
    text = _RE_MANY_DOTS.sub("…", text)
    text = _RE_DOUBLE_DOT.sub(".", text)
    text = _RE_REPEATED_BANG_Q.sub(r"\1", text)
    text = text.replace("...", "…")

    # --- 7) Ensure one space after sentence enders ---
    # (callable repl skips decimals like 3.5 and abbreviations like U.S.)
    text = _RE_SPACE_AFTER_ENDER.sub(_space_after_ender_repl, text)

    # --- 8) Em dash spacing; tight hyphens ---
    text = _RE_EM_DASH_SPACE.sub(" — ", text)
    text = _RE_HYPHEN_SPACE.sub("-", text)

    # --- 9) Tidy spaces around newlines ---
    text = _RE_SPACE_BEFORE_NEWLINE.sub("\n", text)
    text = _RE_SPACE_AFTER_NEWLINE.sub("\n", text)

    lines = []
    for raw_line in text.split("\n"):
        # Strip leading stray punctuation (keep ellipsis and quotes/parens)
        line = _RE_LEADING_PUNCT.sub("", raw_line)

        leading_tabs = len(line) - len(line.lstrip("\t"))
        core = line.lstrip("\t")
        core = core.lstrip(" ")
        core = _RE_MULTI_SPACE.sub(" ", core)
        line = ("\t" * leading_tabs) + core
        lines.append(line.rstrip())
    text = "\n".join(lines)

    # Capitalize standalone lowercase "i" (and "i'll", "i'm", "i've", "i'd")
    # to "I". Done before the per-line capitalization pass so cap_first sees
    # an already-correct string and doesn't have to special-case the pronoun.
    text = _RE_STANDALONE_I.sub("I", text)

    # --- 10) Capitalization ---
    def cap_first(s: str) -> str:
        for i, ch in enumerate(s):
            if ch.isalpha():
                return s[:i] + ch.upper() + s[i+1:]
        return s

    # Temporarily convert §SHIFT_ENTER§ to newlines for capitalization processing
    temp_text = text.replace("§SHIFT_ENTER§", "\n")

    lines = []
    for line in temp_text.split("\n"):
        line = cap_first(line)
        # Convert trailing comma to period at end of line
        line = _RE_TRAILING_COMMA.sub(".", line)
        # Add period at end of line if no punctuation exists
        if line and line.strip() and not _RE_NO_END_PUNCT.search(line.rstrip()):
            line = line.rstrip() + "."
        # Capitalize after sentence enders
        line = _RE_CAP_AFTER_ENDER.sub(lambda m: m.group(1) + m.group(2).upper(), line)
        lines.append(line)
    temp_text = "\n".join(lines)

    # Convert newlines back to §SHIFT_ENTER§ markers
    text = temp_text.replace("\n", "§SHIFT_ENTER§")

    # --- 11) Place sentence punctuation inside closing smart quote ---
    text = _RE_PUNCT_OUTSIDE_QUOTE.sub(r"\2" + "\u201d", text)

    # --- 12) Restore literal tokens ---
    for placeholder, word in LITERAL_RESTORE.items():
        text = text.replace(placeholder, word)

    # --- 12.5) Re-capitalize line starts after literal restore ---
    # cap_first() ran while protected words were placeholders like
    # "__LIT_RETURN__" (whose first letter is already uppercase), so a line
    # STARTING with a protected word came back lowercase ("return to sender
    # was..."). Idempotent: lines already capitalized are left untouched.
    temp_text = text.replace("§SHIFT_ENTER§", "\n")
    temp_text = "\n".join(cap_first(line) for line in temp_text.split("\n"))
    text = temp_text.replace("\n", "§SHIFT_ENTER§")

    # --- 13) Restore quoted sections with actual quote marks ---
    for i, quoted_text in enumerate(quoted_sections):
        text = text.replace(f"__QUOTED_{i}__", f'"{quoted_text}"')

    # --- 14) Fix email/URL formatting ---
    text = _RE_EMAIL_AT_WORD.sub(r"\1@\2.\3", text)
    for pat, repl in _EMAIL_TLD_FIXES:
        text = pat.sub(repl, text)

    # --- 15) Fix time formatting ---
    # "11. 30 p. m." → "11:30 PM", "3:15 a. m." → "3:15 AM", etc.
    text = _RE_TIME_FORMAT.sub(_fix_time_ampm, text)

    return text

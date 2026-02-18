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
    "new line": "__LIT_NEWLINE__",
    "return": "__LIT_NEWLINE__",
    "line break": "__LIT_NEWLINE__",
    "new paragraph": "__LIT_NEWPARA__",
    "paragraph break": "__LIT_NEWPARA__",
    "question mark": "__LIT_QMARK__",
    "exclamation point": "__LIT_EPOINT__",
    "exclamation mark": "__LIT_EPOINT__",
    "semicolon": "__LIT_SEMICOLON__",
    "colon": "__LIT_COLON__",
    "apostrophe": "__LIT_APOSTROPHE__",
    "quote": "__LIT_QUOTE__",
    "hyphen": "__LIT_HYPHEN__",
    "dash": "__LIT_DASH__",
    "ellipsis": "__LIT_ELLIPSIS__",
    "dot dot dot": "__LIT_ELLIPSIS__",
}

# Auto-compute the restore mapping (placeholder → original word)
# Only keep one entry per unique placeholder (first occurrence wins)
_seen_placeholders = {}
for _word, _ph in LITERAL_REPLACEMENTS.items():
    if _ph not in _seen_placeholders:
        _seen_placeholders[_ph] = _word
LITERAL_RESTORE = _seen_placeholders

# Precompile literal escape patterns: "literal <word>" or "the word <word>"
_LITERAL_PATTERNS = [
    (re.compile(rf"\b(?:literal|the\s+words?)\s+{re.escape(word)}\b", re.IGNORECASE), placeholder)
    for word, placeholder in LITERAL_REPLACEMENTS.items()
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
    (re.compile(r"\bhyphen\b|\bdash\b", re.IGNORECASE), "-"),
    (re.compile(r"\bem\s*dash\b", re.IGNORECASE), "—"),
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
_RE_CAP_AFTER_ENDER = re.compile(r"([.?!…]\s+)([a-z])")

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
    text = _RE_SPACE_AFTER_ENDER.sub(r"\1 ", text)

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

    # --- 13) Restore quoted sections with actual quote marks ---
    for i, quoted_text in enumerate(quoted_sections):
        text = text.replace(f"__QUOTED_{i}__", f'"{quoted_text}"')

    # --- 14) Fix email/URL formatting ---
    text = _RE_EMAIL_AT_WORD.sub(r"\1@\2.\3", text)
    for pat, repl in _EMAIL_TLD_FIXES:
        text = pat.sub(repl, text)

    return text

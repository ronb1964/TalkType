import re

def normalize_text(text: str) -> str:
    """Spoken punctuation -> symbols; tidy punctuation; auto-capitalize; keep newlines/tabs."""
    if not text:
        return text

    # --- 0) Escape sequences for literal words (do NOT convert to punctuation) ---
    # Allow phrases like "literal period" or "the word period" to keep the word "period"
    # instead of converting it to a period symbol.
    text = re.sub(r"\b(?:literal|the\s+word)\s+period\b", "__LIT_PERIOD__", text, flags=re.IGNORECASE)

    # --- 1) Multi-word replacements first (order matters) ---
    replacements = [
        (r"\bnew\s*line\b|\bnewline\b|\breturn\b|\bline\s+break\b", "\n"),
        (r"\bnew\s+paragraph\b|\bparagraph\s+break\b", "\n\n"),
        (r"\btab\b", "\t"),
        (r"\bexclamation\s+point\b|\bexclamation\s+mark\b", "!"),
        (r"\bquestion\s+mark\b", "?"),
        (r"\bfull\s*stop\b", "."),
        (r"\bdot\s+dot\s+dot\b|\bellipsis\b", "…"),
        (r"\bopen\s+parenthesis\b", "("),
        (r"\bclose\s+parenthesis\b", ")"),
        (r"\bopen\s+bracket\b", "["),
        (r"\bclose\s+bracket\b", "]"),
        (r"\bopen\s+brace\b", "{"),
        (r"\bclose\s+brace\b", "}"),
        (r"\bopen\s+quote\b|\bopen\s+quotes\b", "“"),
        (r"\bclose\s+quote\b|\bclose\s+quotes\b", "”"),
    ]
    for pat, repl in replacements:
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)

    # --- 2) Single-word replacements ---
    singles = [
        # Allow optional immediate punctuation after the spoken token (e.g., "comma,", "period.")
        (r"\bcomma\b,?", ","),
        (r"\bsemicolon\b;?", ";"),
        (r"\bcolon\b:?", ":"),
        (r"\bperiod\b\.?", "."),
        (r"\bapostrophe\b", "’"),
        (r"\bquote\b", '"'),
        (r"\bhyphen\b|\bdash\b", "-"),
        (r"\bem\s*dash\b", "—"),
    ]
    for pat, repl in singles:
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)

    # --- 3) Quotes/brackets spacing (no space inside, tidy outside) ---
    text = re.sub(r"(\(|\[|\{)\s+", r"\1", text)   # "( something" -> "(something"
    text = re.sub(r"\s+(\)|\]|\})", r"\1", text)   # "something )" -> "something)"
    text = re.sub(r"(“)\s+", r"\1", text)          # “ Hello -> “Hello
    text = re.sub(r"\s+(”)", r"\1", text)          # Hello ” -> Hello”

    # Remove stray commas right after open quote / before close quote
    text = re.sub(r"“\s*,+", "“", text)
    text = re.sub(r",+\s*”", "”", text)

    # --- 4) Remove spaces before punctuation ---
    text = re.sub(r"\s+([,;:.?!…—-])", r"\1", text)

    # --- 5) Normalize punctuation combos ---
    # commas/semicolons/colons immediately before .?!… → keep the strong ender
    text = re.sub(r"[,;:]\s*([.?!…])", r"\1", text)
    # trailing period after ! or ? → drop it
    text = re.sub(r"([!?])\s*\.", r"\1", text)
    # commas right after ! or ? → drop comma
    text = re.sub(r"([!?])\s*,", r"\1", text)
    # handle any run of commas before a strong ender (,! ,,,! ,,,? etc.)
    text = re.sub(r",+\s*([!?])", r"\1", text)
    # drop commas before a final period
    text = re.sub(r",\s*\.", ".", text)
    # collapse multiple commas anywhere
    text = re.sub(r",\s*,+", ",", text)

    # Semi-odd combos: prefer ':' over '-:' or ':-'
    text = re.sub(r"-\s*:", ":", text)
    text = re.sub(r":\s*-", ":", text)

    # --- 6) Collapse punctuation runs; handle ellipsis ---
    text = re.sub(r"\.{4,}", "…", text)                # 4+ dots → ellipsis
    text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)     # stray double dot → single
    text = re.sub(r"([!?])\1+", r"\1", text)           # !!! → !, ??? → ?
    text = text.replace("...", "…")

    # --- 7) Ensure one space after sentence enders (. ? ! …) when followed by text
    # (not end-of-line and not immediately followed by closers/quotes)
    text = re.sub(r"([.?!…])(?!\s|$|[”\)\]\}])", r"\1 ", text)

    # --- 8) Em dash spacing; tight hyphens ---
    text = re.sub(r"\s*—\s*", " — ", text)
    text = re.sub(r"\s*-\s*", "-", text)

    # --- 9) Tidy spaces around newlines; keep tabs/newlines; avoid stripping leading tabs ---
    text = re.sub(r"[ \t]+\n", "\n", text)   # drop spaces/tabs before newline
    text = re.sub(r"\n[ ]+", "\n", text)     # drop spaces after newline, KEEP tabs

    # Collapse multiple spaces per line, but DO NOT strip leading tabs/indents.
    # Also: remove any spaces that appear immediately after leading tabs.
    lines = []
    for raw_line in text.split("\n"):
        # strip leading runs of stray punctuation at start of each line
        # DO NOT strip spaces or tabs (preserve indentation/intentional leading space)
        # (keep ellipsis and quotes/paren if present)
        line = re.sub(r"^[\.,;:!?]+(?!…)", "", raw_line)

        leading_tabs = len(line) - len(line.lstrip("\t"))
        core = line.lstrip("\t")
        core = core.lstrip(" ")                  # remove a space right after the tabs
        core = re.sub(r"[ ]{2,}", " ", core)     # collapse internal space runs
        line = ("\t" * leading_tabs) + core
        lines.append(line.rstrip())
    text = "\n".join(lines)

    # --- 10) Capitalization: first letter of each paragraph, and after .?!… + space ---
    def cap_first(s: str) -> str:
        for i, ch in enumerate(s):
            if ch.isalpha():
                return s[:i] + ch.upper() + s[i+1:]
        return s

    lines = []
    for line in text.split("\n"):
        line = cap_first(line)
        # Capitalize after (.?!… + space) if next is a-z
        line = re.sub(r"([.?!…]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), line)
        lines.append(line)
    text = "\n".join(lines)

    # --- 11) Place sentence punctuation inside closing smart quote ---
    # Turn ”! -> !”, ”? -> ?”, ”. -> .”, ”, -> ,”, ”; -> ;”, ”: -> :
    text = re.sub(r"”( ?)([!?,;:.])", r"\2”", text)

    # --- 12) Restore literal tokens ---
    text = text.replace("__LIT_PERIOD__", "period")

    return text

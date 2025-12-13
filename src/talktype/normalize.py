import re

def normalize_text(text: str) -> str:
    """Spoken punctuation -> symbols; tidy punctuation; auto-capitalize; keep newlines/tabs."""
    if not text:
        return text

    # --- 0) Handle quoted text - preserve everything inside quotes as literal ---
    # This allows users to say "open quote new paragraph close quote" and get literal text
    # Extract quoted sections and protect them from processing
    quoted_sections = []
    def save_quoted(match):
        quoted_sections.append(match.group(1))
        return f"__QUOTED_{len(quoted_sections)-1}__"

    # Match text between "open quote/quotes" and "close quote/quotes"
    # Allow commas, periods, and other punctuation around the quoted text
    text = re.sub(
        r'\b(?:open\s+quotes?)[,.\s]+(.*?)[,.\s]+(?:close\s+quotes?)\b',
        save_quoted,
        text,
        flags=re.IGNORECASE
    )

    # --- 0.1) Escape sequences for literal words ---
    # Allow phrases like "literal period" or "the word period" to output the word instead of the command
    # Store literal words with placeholders that will be restored later
    literal_replacements = {
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
    
    # Apply literal escapes (must come before the actual command replacements)
    for word, placeholder in literal_replacements.items():
        # Match "literal <word>" or "the word <word>" or "the words <word>"
        pattern = rf"\b(?:literal|the\s+words?)\s+{re.escape(word)}\b"
        text = re.sub(pattern, placeholder, text, flags=re.IGNORECASE)

    # --- 1) Multi-word replacements first (order matters) ---
    replacements = [
        (r"\s*\bnew\s*line\b[,.\s]*|\bnewline\b|\breturn\b|\bline\s+break\b", "§SHIFT_ENTER§"),
        (r"[,.\s]*\bnew\s+paragraph\b[,.\s]*|\bparagraph\s+break\b[,.\s]*", "§SHIFT_ENTER§§SHIFT_ENTER§"),
        (r"[,.\s]*\bsoft\s+break\b[,.\s]*|\bsoft\s+line\b[,.\s]*", "   "),
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
        line = re.sub(r"^[\s]*[\.,;:!?]+(?!…)", "", raw_line)

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

    # Temporarily convert §SHIFT_ENTER§ to newlines for capitalization processing
    temp_text = text.replace("§SHIFT_ENTER§", "\n")

    lines = []
    for line in temp_text.split("\n"):
        line = cap_first(line)
        # Convert trailing comma to period at end of line (before line break)
        line = re.sub(r",$", ".", line)
        # Add period at end of line if no punctuation exists (before line break)
        # BUT: Don't add period to empty lines (from "new line" / "new paragraph" commands)
        if line and line.strip() and not re.search(r"[.?!…]$", line.rstrip()):
            line = line.rstrip() + "."
        # Capitalize after (.?!… + space) if next is a-z
        line = re.sub(r"([.?!…]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), line)
        lines.append(line)
    temp_text = "\n".join(lines)
    
    # Convert newlines back to §SHIFT_ENTER§ markers
    text = temp_text.replace("\n", "§SHIFT_ENTER§")

    # --- 11) Place sentence punctuation inside closing smart quote ---
    # Turn ”! -> !”, ”? -> ?”, ”. -> .”, ”, -> ,”, ”; -> ;”, ”: -> :
    text = re.sub(r"”( ?)([!?,;:.])", r"\2”", text)

    # --- 12) Restore literal tokens ---
    literal_restore = {
        "__LIT_PERIOD__": "period",
        "__LIT_COMMA__": "comma",
        "__LIT_TAB__": "tab",
        "__LIT_NEWLINE__": "newline",
        "__LIT_NEWPARA__": "new paragraph",
        "__LIT_QMARK__": "question mark",
        "__LIT_EPOINT__": "exclamation point",
        "__LIT_SEMICOLON__": "semicolon",
        "__LIT_COLON__": "colon",
        "__LIT_APOSTROPHE__": "apostrophe",
        "__LIT_QUOTE__": "quote",
        "__LIT_HYPHEN__": "hyphen",
        "__LIT_DASH__": "dash",
        "__LIT_ELLIPSIS__": "ellipsis",
    }
    for placeholder, word in literal_restore.items():
        text = text.replace(placeholder, word)

    # --- 13) Restore quoted sections with actual quote marks ---
    for i, quoted_text in enumerate(quoted_sections):
        # Put the quoted text back, wrapped in smart quotes
        text = text.replace(f"__QUOTED_{i}__", f'"{quoted_text}"')

    # --- 14) Fix email/URL formatting (run LAST to fix any spacing issues) ---
    # Whisper and earlier steps may add spaces in email addresses
    # e.g., "gmail. com" or "@ gmail" - fix these patterns
    
    # First, convert "at" to "@" in email contexts (username at domain.com)
    # Pattern: alphanumeric/dots/underscores, then " at ", then domain
    # Handle both "gmail.com" and "gmail. com" (with space from "dot com" normalization)
    # Match common TLDs: com, org, net, edu, gov, io, co, uk, ca, de, fr, etc.
    text = re.sub(
        r"([a-zA-Z0-9._-]+)\s+at\s+([a-zA-Z0-9.-]+)\s*\.\s*(com|org|net|edu|gov|io|co|uk|ca|de|fr|us|au|jp|cn|in|br|mx|ru|kr|es|it|nl|se|no|fi|pl|cz|hu|ro|gr|pt|ie|nz|za|ae|il|tr|th|vn|ph|id|my|sg|hk|tw)\b",
        r"\1@\2.\3",
        text,
        flags=re.IGNORECASE
    )
    
    # Then fix other email formatting issues
    email_fixes = [
        (r"@\s+", "@"),                           # "@ gmail" → "@gmail"
        (r"\.\s*([Cc]om)\b", ".com"),             # ". Com" or ". com" → ".com"
        (r"\.\s*([Oo]rg)\b", ".org"),             # ". Org" → ".org"
        (r"\.\s*([Nn]et)\b", ".net"),             # ". Net" → ".net"
        (r"\.\s*([Ee]du)\b", ".edu"),             # ". Edu" → ".edu"
        (r"\.\s*([Gg]ov)\b", ".gov"),             # ". Gov" → ".gov"
        (r"\.\s*([Ii]o)\b", ".io"),               # ". Io" → ".io"
        (r"\.\s*([Cc]o)\b", ".co"),               # ". Co" → ".co"
        (r"\.\s*([Uu]k)\b", ".uk"),               # ". Uk" → ".uk"
        (r"\.\s*([Cc]a)\b", ".ca"),               # ". Ca" → ".ca"
        (r"\.\s*([Dd]e)\b", ".de"),               # ". De" → ".de"
        (r"\.\s*([Ff]r)\b", ".fr"),               # ". Fr" → ".fr"
    ]
    for pat, repl in email_fixes:
        text = re.sub(pat, repl, text)

    return text

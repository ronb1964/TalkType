"""Everything a user reads says TuxTalk, not TalkType (0.15.0 rename).

TalkType is another company's registered trademark for dictation software.
Old names survive only where they are invisible or needed to find an old
install: the D-Bus names (kept so an old GNOME extension keeps working until
the next logout), file patterns that find old AppImages, the rename module,
and the deliberate "Formerly TalkType" in the About window.
"""
import ast
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "tuxtalk"
EXT = (pathlib.Path(__file__).resolve().parent.parent / "gnome-extension"
       / "talktype@ronb1964.github.io" / "extension.js")

ALLOWED = (
    "Formerly TalkType",
    "io.github.ronb1964.TalkType",      # D-Bus name and interface (kept)
    "/io/github/ronb1964/TalkType",      # D-Bus object path (kept)
    "TalkType-*.AppImage",              # finds an old downloaded AppImage
    "TalkType.AppImage",                # the old installed path, adopted on start
)


# Whole strings that are the old name on purpose, per file.
ALLOWED_EXACT = {
    "settings_backup.py": {"TalkType"},     # backups saved before the rename still load
}


def _strings(tree):
    """Every string constant except docstrings (those are for developers)."""
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(
                    getattr(node.body[0], "value", None), ast.Constant):
                docs.add(id(node.body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            yield node.lineno, node.value


def test_python_ui_text_says_tuxtalk():
    bad = []
    for f in sorted(SRC.glob("*.py")):
        if f.name == "rename_migration.py":
            continue
        for line, s in _strings(ast.parse(f.read_text())):
            if s in ALLOWED_EXACT.get(f.name, ()):
                continue
            rest = s
            for ok in ALLOWED:
                rest = rest.replace(ok, "")
            if "TalkType" in rest:
                bad.append(f"{f.name}:{line}: {s[:80]!r}")
    assert not bad, "\n".join(bad)


def test_extension_ui_text_says_tuxtalk():
    text = EXT.read_text()
    bad = []
    for m in re.finditer(r"(['\"`])((?:\\.|(?!\1).)*?)\1", text):
        s = m.group(2)
        rest = s
        for ok in ALLOWED:
            rest = rest.replace(ok, "")
        if "TalkType" in rest:
            bad.append(f"extension.js:{text[:m.start()].count(chr(10)) + 1}: {s[:80]!r}")
    assert not bad, "\n".join(bad)


def test_about_says_formerly_talktype():
    assert "Formerly TalkType" in (SRC / "tray.py").read_text()

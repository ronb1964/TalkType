"""TuxTalk's emoji show on every computer, with or without an emoji font.

On a Mint without Noto Color Emoji the Preferences hints were boxes with
"01F4A1" in them (issue #19). TuxTalk now carries the emoji it uses in a
font of its own (packaging/build-emoji-font.py) and loads it in every
process (ui_style.prepare_windows). These tests fail as soon as a screen
uses an emoji the font doesn't have, so a new one can't slip into a release.
"""
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONTS = ROOT / "src" / "tuxtalk" / "fonts"

_spec = importlib.util.spec_from_file_location("build_emoji_font",
                                               ROOT / "packaging" / "build-emoji-font.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)


def _bundled():
    return set(build.CONTENTS.read_text(encoding="utf-8").split())


def test_every_emoji_tuxtalk_shows_is_in_its_own_font():
    missing = sorted(build.emoji_needed() - _bundled())
    assert not missing, (
        f"{''.join(missing)} not in TuxTalk's emoji font: "
        "run python3 packaging/build-emoji-font.py and commit the font")


def test_the_font_carries_nothing_tuxtalk_no_longer_uses():
    unused = sorted(_bundled() - build.emoji_needed())
    assert not unused, f"{''.join(unused)} no longer used: rebuild the font to drop them"


def test_the_font_file_holds_what_its_list_says():
    """The list could be updated and the font forgotten. CI installs
    fontTools for this; elsewhere it's skipped without it."""
    ttlib = pytest.importorskip("fontTools.ttLib")
    cmap = ttlib.TTFont(build.FONT).getBestCmap()
    assert {ch for ch in _bundled() if ord(ch) not in cmap} == set()


def test_text_symbols_are_found_in_the_code_and_the_rest_is_emoji():
    """The scan sees symbols in what TuxTalk shows, not in its docstrings or
    in letters of other scripts (日本語, Español)."""
    found = build.symbols_in_source()
    assert "💡" in found and "✓" in found
    assert not {"日", "ñ", " "} & found


def test_the_font_ships_with_its_license():
    assert "SIL Open Font License" in (FONTS / "LICENSE").read_text()
    notice = (ROOT / "THIRD_PARTY_LICENSES.md").read_text()
    assert "Noto Color Emoji" in notice and build.NOTO_COMMIT in notice


def test_a_process_without_fontconfig_still_opens_its_windows(monkeypatch, caplog):
    """The font is a nicety: no libfontconfig means boxes, not a crash."""
    from tuxtalk import ui_style

    def no_library(name):
        raise OSError(f"{name}: cannot open shared object file")
    monkeypatch.setattr(ui_style.ctypes, "CDLL", no_library)
    ui_style.load_emoji_font()
    assert "No fontconfig" in caplog.text

"""prefs_style.css must actually reach the widgets it styles.

The stylesheet was attached to the Preferences *window's* style context. In
GTK3 a window-scoped provider does not reach that window's children — measured
with a real widget: a child button kept the theme default (50,50,50) under a
window-scoped provider that set it red, and took the colour correctly from a
screen-wide one. So every rule in the file except `window` silently did nothing
for as long as it existed: roughly 70 selectors covering buttons, tabs, entries,
switches, scales and scrollbars had never once rendered.

The fix has two halves and BOTH are required:

  1. install the provider screen-wide, so it reaches child widgets at all
  2. scope every selector to .talktype-prefs, so it does not restyle the help
     dialog and every other GTK window in the process — which is exactly what
     the original window-scoping was trying to prevent

Half a fix is worse than none: screen-wide with unscoped selectors would repaint
unrelated windows.
"""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = ROOT / "src/talktype/prefs_style.css"
PREFS = ROOT / "src/talktype/prefs.py"

SCOPE_CLASS = "talktype-prefs"


def _top_level_selectors():
    """Yield (line_number, selector) for each top-level rule in the stylesheet."""
    depth = 0
    for n, line in enumerate(CSS.read_text().splitlines(), start=1):
        stripped = line.strip()
        if (depth == 0 and stripped.endswith("{")
                and not stripped.startswith(("/*", "*", "@"))):
            yield n, stripped[:-1].strip()
        depth += line.count("{") - line.count("}")


def test_every_selector_is_scoped_to_the_prefs_window():
    """An unscoped selector would repaint unrelated windows in this process."""
    unscoped = [
        f"line {n}: {sel}"
        for n, sel in _top_level_selectors()
        if SCOPE_CLASS not in sel
    ]
    assert not unscoped, (
        f"These selectors are not scoped to .{SCOPE_CLASS}, so once the "
        f"provider is installed screen-wide they would restyle every GTK "
        f"window in the process: {unscoped}"
    )


def test_stylesheet_is_installed_screen_wide():
    """Window scope was the original bug — it never reached child widgets."""
    text = PREFS.read_text()
    loader = text.split("def _load_css", 1)[1].split("\n    def ", 1)[0]
    assert "add_provider_for_screen" in loader, (
        "_load_css does not install the stylesheet screen-wide, so it cannot "
        "reach any child widget and the whole file is dead again."
    )


def test_prefs_window_carries_the_scope_class():
    """Without the class, every scoped selector matches nothing."""
    text = PREFS.read_text()
    assert f'add_class(PREFS_STYLE_CLASS)' in text, (
        "The Preferences window never gets the scope class added, so the "
        "scoped stylesheet matches nothing at all."
    )
    assert f'PREFS_STYLE_CLASS = "{SCOPE_CLASS}"' in text, (
        f"PREFS_STYLE_CLASS must stay in step with the .{SCOPE_CLASS} prefix "
        f"used throughout prefs_style.css."
    )


def test_stylesheet_parses():
    """A syntax error would silently drop the rest of the file."""
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    provider = Gtk.CssProvider()
    try:
        provider.load_from_path(str(CSS))
    except Exception as exc:  # GLib.Error
        pytest.fail(f"prefs_style.css does not parse: {exc}")

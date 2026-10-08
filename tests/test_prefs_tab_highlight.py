"""Preferences opened on a tab highlights that tab.

Opening Preferences straight to a tab (tray -> Your Stats..., or --tab) showed
the right page while the tab bar still highlighted "General" on KDE. The tabs
had a 150 ms CSS transition, and Preferences switches tab before the window's
first frame, so the transition never ran and the old highlight stayed until
something forced a redraw. Reproduced on KDE Plasma 6.7 and fixed by removing
only that transition (2026-10-08).
"""
import pathlib
import re

CSS = (pathlib.Path(__file__).resolve().parent.parent
       / "src" / "talktype" / "prefs_style.css").read_text()


def _rules(selector_part):
    return [body for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", CSS)
            if selector_part in sel]


def test_notebook_tabs_have_no_transition():
    tab_rules = _rules("notebook > header > tabs > tab")
    assert tab_rules, "the tab rules moved; update this test"
    for body in tab_rules:
        assert not re.search(r"\btransition\s*:", body)

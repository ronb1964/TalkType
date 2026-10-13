"""Preferences opened on a tab highlights that tab.

Preferences can open straight to a tab (tray -> Your Stats..., or --tab), and
switches tab before the window's first frame. A CSS transition on the tabs
never runs then, so on KDE the tab bar would keep highlighting "General" until
something forced a redraw; the tabs therefore have no transition.
"""
import pathlib
import re

CSS = (pathlib.Path(__file__).resolve().parent.parent
       / "src" / "tuxtalk" / "prefs_style.css").read_text()


def _rules(selector_part):
    return [body for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", CSS)
            if selector_part in sel]


def test_notebook_tabs_have_no_transition():
    tab_rules = _rules("notebook > header > tabs > tab")
    assert tab_rules, "the tab rules moved; update this test"
    for body in tab_rules:
        assert not re.search(r"\btransition\s*:", body)

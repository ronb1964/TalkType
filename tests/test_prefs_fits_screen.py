"""Preferences must fit a 1280x800 or 1366x768 screen with its buttons showing.

The window can never be smaller than its minimum height, so one tab whose
content does not scroll forces that height on every tab, and maximizing
cannot pull the Help/Cancel/Apply/OK row back onto the screen. Every tab
scrolls instead, and the window opens at its usual height capped to the
monitor.
"""
from types import SimpleNamespace

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from tuxtalk import prefs  # noqa: E402
from tuxtalk import ui_style  # noqa: E402
from tuxtalk.config import Settings  # noqa: E402
from dataclasses import asdict  # noqa: E402


def _fake_display(height):
    """A display whose primary monitor's work area is *height* tall."""
    workarea = SimpleNamespace(height=height, width=1280)
    monitor = SimpleNamespace(get_workarea=lambda: workarea)
    return SimpleNamespace(get_primary_monitor=lambda: monitor,
                           get_n_monitors=lambda: 1,
                           get_monitor=lambda i: monitor)


def _build(monkeypatch, screen_height):
    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    display = _fake_display(screen_height)
    monkeypatch.setattr(ui_style.Gdk.Display, "get_default", lambda: display)
    monkeypatch.setattr(prefs.PreferencesWindow, "load_config",
                        lambda self: asdict(Settings()))
    monkeypatch.setattr(prefs, "load_custom_commands", lambda: {})
    monkeypatch.setattr(prefs.PreferencesWindow, "_watch_custom_commands_file",
                        lambda self: None)
    monkeypatch.setattr(prefs.PreferencesWindow, "_show_window", lambda self: None)
    w = prefs.PreferencesWindow()
    # Hidden widgets measure as zero; show the contents without mapping the window.
    w.window.get_child().show_all()
    return w


def _min_height(w):
    return w.window.get_child().get_preferred_height()[0]


def test_every_tab_scrolls_so_the_window_can_shrink(monkeypatch):
    w = _build(monkeypatch, 2000)
    try:
        for i in range(w.notebook.get_n_pages()):
            page = w.notebook.get_nth_page(i)
            assert isinstance(page, Gtk.ScrolledWindow), w.notebook.get_tab_label_text(page)
        # Small enough for a 768 px screen less its panel, title bar and the
        # window's own frame.
        assert _min_height(w) < 520
    finally:
        w.window.destroy()


def test_short_screen_caps_the_opening_height(monkeypatch):
    w = _build(monkeypatch, 768)
    try:
        _width, height = w.window.get_default_size()
        assert 0 < height <= 768 - 96
        assert _min_height(w) <= height
    finally:
        w.window.destroy()


def test_tall_screen_opens_with_words_shown_whole(monkeypatch):
    """At full size the Words tab (Your Words and the snippets) needs no scrolling."""
    w = _build(monkeypatch, 2000)
    try:
        _width, height = w.window.get_default_size()
        snippets = w.notebook.get_nth_page(3)
        assert w.notebook.get_tab_label_text(snippets) == "Words"
        content = snippets.get_child()
        if isinstance(content, Gtk.Viewport):
            content = content.get_child()
        assert height >= content.get_preferred_height()[1] + 150
    finally:
        w.window.destroy()

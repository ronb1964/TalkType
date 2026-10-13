"""Preferences must still open when the capture-scroll controller is missing.

Gtk.EventControllerScroll only exists from GTK 3.24. Its fallback branch named
a `logger` that prefs.py never defined, so the NameError escaped from
create_ui and the whole window failed to open instead of just skipping the
scroll controller.
"""
from types import SimpleNamespace

from tuxtalk import prefs as P
from tuxtalk.prefs import PreferencesWindow


def test_missing_scroll_controller_is_skipped_not_fatal(monkeypatch, capsys):
    # A Gtk without EventControllerScroll, like GTK older than 3.24.
    monkeypatch.setattr(P, "Gtk", SimpleNamespace())
    window = SimpleNamespace()

    PreferencesWindow._install_capture_scroll(window, object())

    assert not hasattr(window, "_scroll_controllers")
    assert "Could not install capture scroll controller" in capsys.readouterr().out

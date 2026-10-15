"""Rows that depend on a setting must be hidden when Preferences opens.

Hiding a row while its tab is built isn't enough: window.show_all() makes it
visible again, so a user with auto-timeout off would see a minutes spinner
that does nothing. Hiding it later on a timer makes it flash on screen first.
"""
from types import SimpleNamespace

from tuxtalk.prefs import PreferencesWindow


class FakeWidget:
    def __init__(self):
        self.visible = False

    def set_visible(self, value):
        self.visible = value


class FakeWindow:
    """show_all() shows every child, as Gtk's does."""

    def __init__(self, children):
        self.children = children
        self.presented = False

    def show_all(self):
        for child in self.children:
            child.visible = True

    def present(self):
        self.presented = True


def _stub(config):
    rows = {name: FakeWidget() for name in
            ("timeout_label", "timeout_spin", "lang_label", "lang_combo",
             "auto_langs_label", "auto_langs_button")}
    stub = SimpleNamespace(config=config, window=FakeWindow(list(rows.values())),
                           ok_btn=SimpleNamespace(grab_default=lambda: None), **rows)
    for name in ("_update_timeout_ui_state", "_update_language_ui_state", "_show_language_rows"):
        setattr(stub, name, getattr(PreferencesWindow, name).__get__(stub))
    return stub


def test_rows_for_settings_that_are_off_stay_hidden_after_show_all():
    stub = _stub({"auto_timeout_enabled": False, "language_mode": "auto"})

    PreferencesWindow._show_window(stub)

    assert stub.window.presented
    assert not stub.timeout_label.visible and not stub.timeout_spin.visible
    assert not stub.lang_label.visible and not stub.lang_combo.visible
    # Auto-detect shows its language list instead.
    assert stub.auto_langs_label.visible and stub.auto_langs_button.visible


def test_rows_for_settings_that_are_on_are_shown():
    stub = _stub({"auto_timeout_enabled": True, "language_mode": "manual"})

    PreferencesWindow._show_window(stub)

    assert stub.timeout_label.visible and stub.timeout_spin.visible
    assert stub.lang_label.visible and stub.lang_combo.visible
    assert not stub.auto_langs_label.visible and not stub.auto_langs_button.visible

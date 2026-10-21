"""TuxTalk never types into a password field.

The words may be the password itself, so in a password field a dictation
(snippets included), Paste Last Dictation and a voice edit type nothing, and
the text stays out of Recent Dictations and notifications. Whether the cursor
is in one comes from the accessibility bus (atspi_helper); whenever that can't
answer, quickly, typing goes ahead as it always did.
"""
import logging
import time
import types

import numpy as np
import pytest
from gi.repository import GLib

from tuxtalk import app, atspi_helper, history, screen_message

ACTIVE = 1 << atspi_helper._STATE_ACTIVE
FOCUSED = 1 << atspi_helper._STATE_FOCUSED
SHOWING = 1 << atspi_helper._STATE_SHOWING
PASSWORD = atspi_helper._ROLE_PASSWORD_TEXT
TEXT = 61      # ATSPI_ROLE_TEXT


# --- the app: nothing typed, nothing kept ------------------------------------------

@pytest.fixture
def desktop(monkeypatch):
    """Everything TuxTalk would do to the desktop, recorded."""
    seen = {"typed": [], "history": [], "notes": [], "beeps": [], "labels": []}
    monkeypatch.setattr(app, "_inject_text",
                        lambda text, mode, t0, one_block=False: seen["typed"].append(text) or "ok")
    monkeypatch.setattr(history, "add_entry",
                        lambda text, replaces=None: seen["history"].append(text))
    monkeypatch.setattr(app, "_notify", lambda title, body: seen["notes"].append(body))
    monkeypatch.setattr(app, "_beep", lambda on, *tone, **k: seen["beeps"].append(tone))
    monkeypatch.setattr(screen_message, "show_over_active_window",
                        lambda text, **k: seen["labels"].append(text))
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: None)
    monkeypatch.setattr(app, "_usage_stats", False, raising=False)
    seen["password"] = False
    monkeypatch.setattr(atspi_helper, "focused_is_password", lambda: seen["password"])
    return seen


def dictate(monkeypatch, said="my secret is swordfish"):
    monkeypatch.setattr(app, "_transcribe_audio", lambda audio, language: said)
    frames = [(np.ones(app.SAMPLE_RATE, dtype=np.int16) * 1000).tobytes()]
    app._transcribe_and_inject(frames, app.SAMPLE_RATE, beeps_on=True,
                               smart_quotes=False, notify_on=True)


def test_a_dictation_in_a_password_field_is_not_typed_or_kept(desktop, monkeypatch, caplog):
    desktop["password"] = True
    with caplog.at_level(logging.INFO, logger="tuxtalk.app"):
        dictate(monkeypatch)
    assert desktop["typed"] == [] and desktop["history"] == []
    # Not even in the "Transcribed: …" notification.
    assert not any("swordfish" in n for n in desktop["notes"])
    assert desktop["beeps"] == [app.CANCEL_BEEP]
    assert desktop["labels"] == [app.PASSWORD_FIELD_LABEL]
    assert "password field" in caplog.text and "swordfish" not in caplog.text


def test_a_dictation_anywhere_else_is_typed_and_kept(desktop, monkeypatch):
    dictate(monkeypatch)
    assert len(desktop["typed"]) == 1 and "swordfish" in desktop["typed"][0]
    assert len(desktop["history"]) == 1
    assert desktop["labels"] == []


def test_paste_last_dictation_types_nothing_in_a_password_field(desktop, monkeypatch):
    monkeypatch.setattr(history, "get_entries", lambda: ["my secret is swordfish"])
    cfg = types.SimpleNamespace(beeps=True, auto_space=True, injection_mode="type")
    desktop["password"] = True
    app._paste_last_dictation(cfg)
    assert desktop["typed"] == []
    assert desktop["labels"] == [app.PASSWORD_FIELD_LABEL]
    desktop["password"] = False
    app._paste_last_dictation(cfg)
    assert desktop["typed"] == ["my secret is swordfish "]


# --- the question: which widget has the focus, and is it a password field ----------

class FakeA11yBus:
    """The accessibility bus as call_sync sees it: apps, their windows and
    widgets, each a (bus name, path) pair like the real ones."""

    def __init__(self):
        self.nodes = {}
        self.apps = self._add(("registry", "root"))["children"]

    def _add(self, ref, **node):
        self.nodes[ref] = dict(dict(name="", role=0, states=0, children=[], collection=True,
                                    hang=False), **node)
        return self.nodes[ref]

    def app(self, name, focus_role, active=True, collection=True, hang=False):
        """An app with one window holding a text box and the focused widget,
        of *focus_role*. *collection* False is a Qt app: no Collection
        interface, so it is walked. *hang*: it never answers."""
        def ref(path):
            return (f":{name}", path)
        common = dict(collection=collection, hang=hang)
        self._add(ref("/2"), role=focus_role, states=SHOWING | FOCUSED, **common)
        self._add(ref("/3"), role=TEXT, states=SHOWING, **common)
        self._add(ref("/1"), states=SHOWING | (ACTIVE if active else 0),
                  children=[ref("/3"), ref("/2")], **common)
        self._add(ref("/root"), name=name, children=[ref("/1")], **common)
        self.apps.append(ref("/root"))

    def call_sync(self, name, path, interface, method, args, reply_type, flags, timeout_ms,
                  cancellable):
        if (name, path) == (atspi_helper._REGISTRY, atspi_helper._ROOT):
            name, path = "registry", "root"
        node = self.nodes[(name, path)]
        if node["hang"]:
            time.sleep(timeout_ms / 1000)
            raise GLib.Error("Timeout was reached")
        if method == "GetChildren":
            return GLib.Variant("(a(so))", (node["children"],))
        if method == "GetState":
            return GLib.Variant("(au)", ([node["states"] & 0xFFFFFFFF, node["states"] >> 32],))
        if method == "GetRole":
            return GLib.Variant("(u)", (node["role"],))
        if method == "Get":
            return GLib.Variant("(v)", (GLib.Variant("s", node["name"]),))
        if method == "GetMatches":
            if not node["collection"]:
                raise GLib.Error("No such interface “org.a11y.atspi.Collection”")
            found = [c for c in node["children"] if self.nodes[c]["states"] & FOCUSED]
            return GLib.Variant("(a(so))", (found,))
        raise AssertionError(f"unexpected call {method}")


@pytest.fixture
def bus(monkeypatch):
    fake = FakeA11yBus()
    monkeypatch.setattr(atspi_helper, "_a11y_bus", lambda: fake)
    return fake


def test_a_focused_password_field_is_found(bus):
    bus.app("gedit", PASSWORD)
    assert atspi_helper.focused_is_password() is True


def test_a_focused_text_box_is_not_a_password_field(bus):
    bus.app("gedit", TEXT)
    assert atspi_helper.focused_is_password() is False


def test_qt_apps_without_the_collection_interface_are_walked(bus):
    bus.app("kwrite", PASSWORD, collection=False)
    assert atspi_helper.focused_is_password() is True


def test_a_password_field_in_a_window_in_the_background_doesnt_count(bus):
    bus.app("seahorse", PASSWORD, active=False)
    assert atspi_helper.focused_is_password() is False


def test_no_accessibility_bus_means_typing_as_usual(monkeypatch):
    monkeypatch.setattr(atspi_helper, "_a11y_bus", lambda: None)
    assert atspi_helper.focused_is_password() is False


def test_a_bus_that_errors_means_typing_as_usual(monkeypatch):
    def broken():
        raise GLib.Error("The name org.a11y.Bus was not provided by any .service files")
    monkeypatch.setattr(atspi_helper, "_a11y_bus", broken)
    assert atspi_helper.focused_is_password() is False


def test_an_answer_in_an_unexpected_shape_means_typing_as_usual(bus, monkeypatch):
    bus.app("gedit", PASSWORD)
    monkeypatch.setattr(atspi_helper, "_states", lambda *a: "not a number")
    assert atspi_helper.focused_is_password() is False


def test_a_hung_app_is_skipped_in_time(bus):
    """An app that never answers costs one call's timeout, then the next
    app is asked."""
    bus.app("frozen", TEXT, hang=True)
    bus.app("gedit", PASSWORD)
    started = time.monotonic()
    assert atspi_helper.focused_is_password() is True
    assert time.monotonic() - started < atspi_helper.BUDGET_S


def test_a_bus_where_everything_hangs_gives_up_within_the_budget(bus, monkeypatch):
    for n in range(5):
        bus.app(f"frozen{n}", PASSWORD, hang=True)
    started = time.monotonic()
    assert atspi_helper.focused_is_password() is False
    took = time.monotonic() - started
    assert took < atspi_helper.BUDGET_S + atspi_helper.CALL_TIMEOUT_MS / 1000

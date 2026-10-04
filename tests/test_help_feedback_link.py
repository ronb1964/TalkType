"""The Help window offers a feedback link, and never asks for feedback itself.

Ron's rule: nothing in TalkType pops up asking for feedback, but a link people
can go looking for in Help is welcome (2026-10-03). The link sits under the
tabs so it's there whichever tab is open.
"""
import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from talktype import help_dialog  # noqa: E402


def _widgets(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from _widgets(child)


@pytest.fixture
def dialog(monkeypatch):
    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    shown = []
    # Build the window without putting it on screen.
    monkeypatch.setattr(Gtk.Dialog, "show_all", lambda self: shown.append(self))
    monkeypatch.setattr(Gtk.Dialog, "present", lambda self: None)
    help_dialog.show_help_dialog()
    yield shown[0]
    shown[0].destroy()


def test_help_has_a_feedback_link_to_discussions(dialog):
    links = [w for w in _widgets(dialog) if isinstance(w, Gtk.LinkButton)]
    assert [l.get_uri() for l in links] == [help_dialog.FEEDBACK_URL]
    assert help_dialog.FEEDBACK_URL == "https://github.com/ronb1964/TalkType/discussions"


def test_the_link_is_outside_the_tabs_so_every_tab_shows_it(dialog):
    link = next(w for w in _widgets(dialog) if isinstance(w, Gtk.LinkButton))
    notebook = next(w for w in _widgets(dialog) if isinstance(w, Gtk.Notebook))
    assert link not in list(_widgets(notebook))


def test_clicking_the_link_does_not_close_help(dialog):
    """Action-area buttons close Help (its response handler destroys it), so
    the link must not be one of them."""
    link = next(w for w in _widgets(dialog) if isinstance(w, Gtk.LinkButton))
    assert dialog.get_response_for_widget(link) == Gtk.ResponseType.NONE


def test_troubleshooting_links_can_be_clicked(dialog):
    markup = " ".join(w.get_label() or "" for w in _widgets(dialog) if isinstance(w, Gtk.Label))
    assert '<a href="https://github.com/ronb1964/TalkType/issues"' in markup
    assert f'<a href="{help_dialog.FEEDBACK_URL}"' in markup

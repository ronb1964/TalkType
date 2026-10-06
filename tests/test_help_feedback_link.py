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


def _help_labels(dialog):
    return [w for w in _widgets(dialog) if isinstance(w, Gtk.Label) and w.get_use_markup()]


def test_every_help_tab_is_valid_markup(dialog):
    """A stray & or < leaves a whole tab blank (GTK drops bad markup)."""
    from gi.repository import Pango
    labels = _help_labels(dialog)
    assert labels
    import re
    for label in labels:
        # GTK labels add <a href> links on top of Pango markup.
        markup = re.sub(r"</?a\b[^>]*>", "", label.get_label())
        Pango.parse_markup(markup, -1, "\0")   # raises on bad markup
        assert label.get_text().strip()


def test_help_lists_every_tray_preset(dialog):
    """Help listed 5 of the 7 old presets; it must name each of today's."""
    from talktype import recommend
    text = "\n".join(l.get_text() for l in _help_labels(dialog))
    for preset in recommend.presets("en", recommend.Hardware(None)):
        assert f"{preset.label}:" in text, f"Help doesn't mention the {preset.label} preset"

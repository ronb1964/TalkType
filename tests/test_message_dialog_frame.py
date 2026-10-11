"""Every TalkType message box gets the desktop's own window frame.

Gtk.MessageDialog installs an empty titlebar of its own, so GTK draws the
frame and the desktop never does. On KDE that frame has square corners while
every other TalkType window gets KDE's rounded one (Ron, 2026-10-10, on the
"You're Up to Date!" box). ui_style.message_dialog() removes that titlebar;
checked in the fedora44-KDE and ubuntu26.04 VMs.
"""
import pathlib
import re

import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "talktype"


@pytest.fixture
def Gtk():
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    return Gtk


def test_the_desktop_draws_the_frame(Gtk):
    from talktype.ui_style import message_dialog
    dialog = message_dialog(message_type=Gtk.MessageType.INFO,
                            buttons=Gtk.ButtonsType.OK, text="You're Up to Date!")
    assert isinstance(dialog, Gtk.MessageDialog)
    assert dialog.get_titlebar() is None
    assert dialog.get_title() == "TalkType"  # the frame shows a title now
    assert dialog.get_deletable()  # an X, like Escape, answers the box


def test_a_box_without_buttons_has_no_close_button(Gtk):
    """'Checking for Updates...' style boxes close themselves when the work
    is done. Closing one early isn't something to invite with an X."""
    from talktype.ui_style import message_dialog
    dialog = message_dialog(buttons=Gtk.ButtonsType.NONE, text="Working...")
    assert not dialog.get_deletable()
    assert not message_dialog(text="Working...").get_deletable()


def test_an_explicit_title_is_kept(Gtk):
    from talktype.ui_style import message_dialog
    assert message_dialog(title="Fix a Word", text="x").get_title() == "Fix a Word"


def test_no_module_builds_a_message_dialog_directly():
    """One stock Gtk.MessageDialog anywhere brings the square box back."""
    offenders = [
        f"{path.name}:{n}"
        for path in SRC.glob("*.py") if path.name != "ui_style.py"
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if re.search(r"\bGtk\.MessageDialog\(", line)
    ]
    assert offenders == []

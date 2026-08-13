"""The indicator position control must reflect what actually works.

Preferences used to grey out the position dropdown whenever the session was
Wayland and the GNOME extension was absent, with a tooltip saying positioning
"requires the GNOME extension". That is not how positioning works.

The indicator positions itself with gtk_window_move(). XWayland honours it and
native Wayland ignores it, and the tray launches the dictation service with
GDK_BACKEND=x11,wayland — so the indicator gets XWayland whenever an X display
exists, on any desktop, with no extension involved. Measured on a KDE Plasma
Wayland session with the extension not installed: top-left landed at (20, 20).

So the control was disabled on a machine where it demonstrably works, telling
the user to install an extension that has nothing to do with it.
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_positioning_available_follows_the_x_display(monkeypatch):
    from talktype.recording_indicator import positioning_available

    monkeypatch.setenv("DISPLAY", ":0")
    assert positioning_available() is True, (
        "An X display is present, so the service gets XWayland and "
        "gtk_window_move() is honoured."
    )

    monkeypatch.delenv("DISPLAY", raising=False)
    assert positioning_available() is False, (
        "With no X display the service falls back to native Wayland, which "
        "ignores gtk_window_move() and centres the indicator."
    )


def test_positioning_does_not_depend_on_the_gnome_extension(monkeypatch):
    """The extension never had anything to do with window positioning."""
    from talktype.recording_indicator import positioning_available

    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert positioning_available() is True, (
        "A Wayland session with XWayland available must still allow "
        "positioning — this is exactly Ron's KDE setup, where it was greyed out."
    )


def test_prefs_uses_the_helper_rather_than_guessing_from_the_session():
    """Guards against the old `is_wayland and not has_extension` condition."""
    text = (ROOT / "src/talktype/prefs.py").read_text()
    assert "positioning_available" in text, (
        "prefs.py must ask whether positioning actually works instead of "
        "inferring it from the session type and the GNOME extension."
    )

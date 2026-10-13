"""Messages where the user is looking: a voice-edit problem floats over the
middle of the active window instead of only in the corner notification.
Spec: docs/superpowers/specs/2026-10-12-messages-at-active-window-design.md
"""
import json
import pathlib

import pytest

from tuxtalk import compositor_focus, window_geometry as wg
from tuxtalk.window_geometry import Rect

SRC = pathlib.Path(wg.__file__).parent
EXT = next((SRC.parent.parent / "gnome-extension").glob("*/"))


# --- reading what the KWin script / GNOME extension reported ------------------------

def test_parse_a_report():
    win, output, output_rect = wg.parse_reported("100,200,800,600|DP-6|0,0,3440,1440")
    assert win == Rect(100, 200, 800, 600)
    assert output == "DP-6" and output_rect == Rect(0, 0, 3440, 1440)


def test_parse_a_report_without_an_output_name():
    win, output, output_rect = wg.parse_reported("10,20,30,40||0,0,1920,1080")
    assert output == "" and output_rect == Rect(0, 0, 1920, 1080)


@pytest.mark.parametrize("bad", ["", "nonsense", "1,2,3|x|1,2,3,4", "1,2,3,4|x|y"])
def test_a_bad_report_is_nothing(bad):
    assert wg.parse_reported(bad) is None


# --- compositor coordinates -> where GTK draws ----------------------------------------

def test_unscaled_screen_is_one_to_one():
    monitors = [("DP-6", Rect(0, 0, 3440, 1440))]
    assert wg.to_screen_point(Rect(100, 200, 800, 600), "DP-6", Rect(0, 0, 3440, 1440), monitors) == (500, 500)


def test_a_scaled_screen_is_scaled():
    """Plasma's XWayland default: X apps see physical pixels, KWin reports logical."""
    monitors = [("DP-1", Rect(0, 0, 3840, 2160))]
    point = wg.to_screen_point(Rect(100, 100, 400, 200), "DP-1", Rect(0, 0, 1920, 1080), monitors)
    assert point == (600, 400)


def test_the_window_is_found_on_its_own_monitor():
    monitors = [("HDMI-A-1", Rect(0, 0, 1920, 1080)), ("DP-2", Rect(1920, 0, 2560, 1440))]
    point = wg.to_screen_point(Rect(2020, 100, 400, 200), "DP-2", Rect(1920, 0, 2560, 1440), monitors)
    assert point == (2220, 200)


def test_without_a_name_a_single_monitor_still_scales():
    monitors = [("", Rect(0, 0, 3840, 2160))]
    assert wg.to_screen_point(Rect(0, 0, 200, 100), "", Rect(0, 0, 1920, 1080), monitors) == (200, 100)


def test_without_a_name_several_monitors_are_one_to_one():
    monitors = [("", Rect(0, 0, 1920, 1080)), ("", Rect(1920, 0, 1920, 1080))]
    assert wg.to_screen_point(Rect(2000, 0, 200, 100), "", Rect(1920, 0, 1920, 1080), monitors) == (2100, 50)


# --- which source answers ---------------------------------------------------------------

@pytest.fixture
def sources(monkeypatch):
    monkeypatch.setattr(wg, "screen_monitors", lambda: [("DP-6", Rect(0, 0, 3440, 1440))])
    monkeypatch.setattr(wg, "_reported", lambda: None)
    monkeypatch.setattr(compositor_focus, "focused_rect", lambda: None)
    monkeypatch.setattr(wg, "_x11_active_rect", lambda: None)


def test_the_tray_report_comes_first(sources, monkeypatch):
    monkeypatch.setattr(wg, "_reported", lambda: "100,200,800,600|DP-6|0,0,3440,1440")
    monkeypatch.setattr(compositor_focus, "focused_rect", lambda: Rect(0, 0, 10, 10))
    assert wg.active_window_center() == (500, 500)


def test_then_the_compositor(sources, monkeypatch):
    monkeypatch.setattr(compositor_focus, "focused_rect", lambda: Rect(0, 0, 1000, 400))
    assert wg.active_window_center() == (500, 200)


def test_then_x11(sources, monkeypatch):
    monkeypatch.setattr(wg, "_x11_active_rect", lambda: Rect(10, 10, 100, 100))
    assert wg.active_window_center() == (60, 60)


def test_nobody_knows(sources):
    assert wg.active_window_center() is None


# --- Sway and Hyprland say where their focused window is --------------------------------

def test_sway_focused_rect(monkeypatch):
    tree = {"nodes": [{"type": "con", "focused": True, "app_id": "foot",
                       "rect": {"x": 10, "y": 20, "width": 300, "height": 200}}]}
    monkeypatch.setenv("SWAYSOCK", "/tmp/sway.sock")
    for var in ("HYPRLAND_INSTANCE_SIGNATURE", "NIRI_SOCKET"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(compositor_focus, "_exchange", lambda path, req, read: tree)
    assert compositor_focus.focused_rect() == Rect(10, 20, 300, 200)


def test_hyprland_focused_rect(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "abc")
    monkeypatch.setattr(compositor_focus, "_exchange",
                        lambda path, req, read: json.dumps({"at": [5, 6], "size": [70, 80]}).encode())
    assert compositor_focus.focused_rect() == Rect(5, 6, 70, 80)


# --- the tray keeps the latest report ------------------------------------------------------

def test_the_tray_caches_the_geometry():
    from tuxtalk import dbus_service
    svc = object()
    dbus_service.TuxTalkDBusService.SetFocusedWindowGeometry(svc, "1,2,3,4|DP-6|0,0,10,10")
    assert dbus_service.TuxTalkDBusService.GetFocusedWindowGeometry(svc) == "1,2,3,4|DP-6|0,0,10,10"


# --- KDE and GNOME report it ------------------------------------------------------------------

def test_the_kwin_script_reports_geometry_and_follows_moves():
    from tuxtalk import kwin_focus
    js = kwin_focus.build_script()
    assert "SetFocusedWindowGeometry" in js
    assert "frameGeometryChanged" in js and "output" in js
    assert "SetFocusedWindowClass" in js           # still reports the class


def test_the_gnome_extension_reports_geometry():
    js = (EXT / "extension.js").read_text()
    assert '<method name="SetFocusedWindowGeometry">' in js
    assert "SetFocusedWindowGeometryRemote" in js
    assert "position-changed" in js and "size-changed" in js
    assert json.loads((EXT / "metadata.json").read_text())["version"] == 19


# --- the floating label -------------------------------------------------------------------------

def test_the_label_is_centred_on_the_point():
    from tuxtalk import screen_message
    assert screen_message.place(200, 40, (500, 500), Rect(0, 0, 3440, 1440)) == (400, 480)


def test_the_label_stays_on_the_monitor():
    from tuxtalk import screen_message
    assert screen_message.place(200, 40, (10, 1435), Rect(0, 0, 3440, 1440)) == (0, 1400)


# --- voice edit problems show there -----------------------------------------------------------------

def test_a_voice_edit_problem_floats_over_the_active_window(monkeypatch):
    from tuxtalk import app, screen_message
    shown = []
    monkeypatch.setattr(screen_message, "show", lambda text, center=None: shown.append((text, center)))
    monkeypatch.setattr(wg, "active_window_center", lambda: (500, 500))
    monkeypatch.setattr(app, "_notify", lambda *a: None)
    monkeypatch.setattr(app, "_beep", lambda *a: None)
    app._edit_problem("no_selection", False)
    assert shown and shown[0][1] == (500, 500) and shown[0][0] == "Select some text first"


# --- Ron, 2026-10-12: it faded before he finished reading it ---------------------------------

def test_long_enough_to_read():
    from tuxtalk import screen_message
    assert screen_message.reading_seconds("Select some text first") == 4.0
    assert 4.0 < screen_message.reading_seconds("Window changed, so the rewrite is in Recent Dictations") <= 8.0
    assert screen_message.reading_seconds(" ".join(["word"] * 60)) == 8.0


def test_the_label_says_it_short_and_the_notification_in_full(monkeypatch):
    from tuxtalk import app, screen_message
    shown, notified = [], []
    monkeypatch.setattr(screen_message, "show", lambda text, center=None: shown.append(text))
    monkeypatch.setattr(wg, "active_window_center", lambda: (1, 1))
    monkeypatch.setattr(app, "_notify", lambda title, msg: notified.append(msg))
    monkeypatch.setattr(app, "_beep", lambda *a: None)
    for kind in app._EDIT_NOTICES:
        shown.clear(); notified.clear()
        app._edit_problem(kind, False)
        assert len(shown[0].split()) <= 7, (kind, shown[0])
        assert notified[0] == app._EDIT_NOTICES[kind]

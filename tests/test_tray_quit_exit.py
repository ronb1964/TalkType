"""Quit from the tray must end the process even with a dialog open.

dialog.run() and the welcome dialog's Gtk.main() spin nested loops;
Gtk.main_quit() from inside one cannot stop the tray's outer loop.
"""
import types

from tuxtalk import tray as tray_mod


def test_quit_queues_a_hard_exit(monkeypatch):
    timers = []
    monkeypatch.setattr(tray_mod, "GLib", types.SimpleNamespace(
        timeout_add=lambda ms, fn: timers.append((ms, fn))))
    quits = []
    monkeypatch.setattr(tray_mod, "Gtk", types.SimpleNamespace(
        main_quit=lambda: quits.append(1)))
    exits = []
    monkeypatch.setattr(tray_mod.os, "_exit", lambda code: exits.append(code))
    t = types.SimpleNamespace(_stop_kwin_focus_provider=lambda: None,
                              _kill_service=lambda: None,
                              preferences_process=None, dbus_service=None)
    t._shut_down = lambda: tray_mod.DictationTray._shut_down(t)
    t._leave_main_loop = lambda: tray_mod.DictationTray._leave_main_loop(t)

    tray_mod.DictationTray.quit_app(t, None)

    assert quits == [1]
    assert len(timers) == 1 and timers[0][0] <= 500
    timers[0][1]()
    assert exits == [0]

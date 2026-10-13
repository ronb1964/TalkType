"""The welcome screen's install buttons: no frozen window, honest results.

Package installs and the pkexec script ran on the GTK thread for up to five
minutes, freezing the window. Fix Typing also reported "Device permissions
configured" and disabled itself when only the ydotoold step was needed and
it had failed. Raw installer output went into Pango markup unescaped.
"""
import threading

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from tuxtalk import recommend as r  # noqa: E402
from tuxtalk import uinput_helper  # noqa: E402
from tuxtalk import welcome_dialog as wd  # noqa: E402


@pytest.fixture
def dialog(monkeypatch):
    """Permissions fine, ydotoold not running: the typing section shows."""
    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    monkeypatch.setattr(r, "detect_hardware", lambda cfg=None: r.Hardware(None, False))
    monkeypatch.setattr(r, "system_language", lambda env=None: "en")
    monkeypatch.setattr(wd, "detect_uinput_access", lambda: (True, ""))
    monkeypatch.setattr(wd, "detect_ydotoold_status",
                        lambda: {"needs_setup": True, "ydotool_installed": True})
    monkeypatch.setattr(wd, "detect_portaudio_status", lambda: {"needs_install": False})
    d = wd.WelcomeDialog(force_gnome=False)
    yield d
    d.destroy()


def test_a_failed_ydotoold_step_is_reported_and_can_be_retried(dialog, monkeypatch):
    dialogs = []
    monkeypatch.setattr(wd, "message_dialog", lambda **k: dialogs.append(k) or None)
    button = dialog.fix_typing_button
    outcome = {"results": ["❌ ydotoold: ydotoold daemon not found."],
               "ydotoold_fixed": False, "uinput_fixed": False, "ydotoold_running": False}
    dialog._finish_fix_typing(button, outcome)
    assert button.get_sensitive()
    assert "Fix Typing" in button.get_label()
    assert "ydotoold daemon not found" in dialog.typing_status_label.get_text()
    assert "permissions configured" not in dialog.typing_status_label.get_text().lower()
    assert dialogs == []          # no "Permissions Configured" box


def test_the_steps_run_only_what_is_still_needed(monkeypatch):
    calls = []
    monkeypatch.setattr(uinput_helper, "setup_ydotoold_service",
                        lambda: calls.append("ydotoold") or (False, "nope"))
    monkeypatch.setattr(uinput_helper, "install_udev_rule_with_pkexec",
                        lambda *a: calls.append("udev") or (True, "ok"))
    monkeypatch.setattr(uinput_helper, "ensure_ydotoold_running", lambda: None)
    monkeypatch.setattr(uinput_helper, "check_ydotoold_running", lambda: False)
    monkeypatch.setattr(wd.time, "sleep", lambda s: None)
    result = wd._fix_typing_steps(do_ydotoold=False, do_uinput=True)
    assert calls == ["udev"]
    assert result["uinput_fixed"] and not result["ydotoold_fixed"]


def test_a_daemon_that_starts_a_moment_later_counts_as_running(monkeypatch):
    answers = iter([False, False, True])
    monkeypatch.setattr(uinput_helper, "setup_ydotoold_service", lambda: (True, "built-in"))
    monkeypatch.setattr(uinput_helper, "check_ydotoold_running", lambda: next(answers))
    monkeypatch.setattr(wd.time, "sleep", lambda s: None)
    assert wd._fix_typing_steps(do_ydotoold=True, do_uinput=False)["ydotoold_running"]


def test_status_text_is_escaped_and_short():
    text = "Installation failed:\n<stdin>: a & b\n" + "\n".join(f"line {i}" for i in range(30))
    markup = wd._status_markup(text, "#f44336")
    assert "&lt;stdin&gt;" in markup and "&amp;" in markup
    assert "line 29" not in markup and "…" in markup
    assert Gtk.Label().set_markup(markup) is None  # valid markup


def test_installs_run_off_the_gtk_thread(dialog, monkeypatch):
    queued = []
    monkeypatch.setattr(wd.GLib, "idle_add", lambda fn, *a: queued.append((fn, a)))
    started = threading.Event()
    release = threading.Event()
    worker = {}

    def work():
        worker["thread"] = threading.current_thread()
        started.set()
        release.wait(2)
        return "done"

    finished = []
    dialog._run_in_background(work, finished.append)
    assert started.wait(2)
    assert worker["thread"] is not threading.main_thread()
    assert not dialog.continue_button.get_sensitive()   # "Set it up" waits
    release.set()
    worker["thread"].join(2)
    fn, args = queued.pop()
    fn(*args)
    assert finished == ["done"]
    assert dialog.continue_button.get_sensitive()


def test_nothing_is_updated_after_the_window_closed(dialog, monkeypatch):
    queued = []
    monkeypatch.setattr(wd.GLib, "idle_add", lambda fn, *a: queued.append((fn, a)))
    finished = []
    done = threading.Event()
    dialog._run_in_background(lambda: done.set() or 1, finished.append)
    assert done.wait(2)
    for _ in range(100):
        if queued:
            break
        threading.Event().wait(0.01)
    dialog._closed = True
    fn, args = queued.pop()
    fn(*args)
    assert finished == []


def test_installs_run_one_at_a_time(dialog, monkeypatch):
    """Install PortAudio and Install ydotool started together: the second
    package-manager run failed on the first one's lock."""
    monkeypatch.setattr(wd.GLib, "idle_add", lambda fn, *a: None)
    first_running = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()

    def first():
        first_running.set()
        release_first.wait(2)

    dialog._run_in_background(first, lambda outcome: None)
    assert first_running.wait(2)
    dialog._run_in_background(second_started.set, lambda outcome: None)
    assert not second_started.wait(0.2)      # waits for the first install
    release_first.set()
    assert second_started.wait(2)

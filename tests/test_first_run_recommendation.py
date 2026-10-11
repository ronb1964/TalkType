"""First run recommends one complete setup instead of asking about CUDA.

The old screen: an unticked "Use your NVIDIA graphics card" box, Full (CUDA,
1.4 GB, preselected) or Light (Vulkan), AMD/Intel never offered, and the model
picked on a later screen. Now one card says what will be set up, and Other
options change it with every choice explained.
"""
import pathlib

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from talktype import recommend as r  # noqa: E402
from talktype import welcome_dialog as wd  # noqa: E402

SRC = (pathlib.Path(wd.__file__)).read_text()


@pytest.fixture
def dialog(monkeypatch):
    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    monkeypatch.setattr(r, "detect_hardware",
                        lambda cfg=None: r.Hardware("NVIDIA GeForce RTX 4070 SUPER", True))
    monkeypatch.setattr(r, "system_language", lambda env=None: "en")
    monkeypatch.setattr(wd, "detect_uinput_access", lambda: (True, ""))
    monkeypatch.setattr(wd, "detect_ydotoold_status", lambda: {"needs_setup": False})
    monkeypatch.setattr(wd, "detect_portaudio_status", lambda: {"needs_install": False})
    d = wd.WelcomeDialog(force_gnome=False)
    yield d
    d.destroy()


def test_card_shows_the_recommendation(dialog):
    s = dialog._current_setup()
    assert (s.model, s.device) == ("parakeet-v3", "vulkan")
    assert "Parakeet on your NVIDIA GeForce RTX 4070 SUPER" in dialog.rec_title.get_text()


def test_changing_the_language_updates_the_card(dialog):
    dialog.lang_combo.set_active_id("ja")
    s = dialog._current_setup()
    assert s.model == "large-v3" and "Whisper Large-v3" in dialog.rec_title.get_text()
    assert not dialog.model_radios["parakeet-v3"].get_sensitive()


def test_unticking_the_graphics_card_uses_the_processor(dialog):
    dialog.gpu_check.set_active(False)
    assert dialog._current_setup().device == "cpu"
    assert "processor" in dialog.rec_title.get_text()


def test_run_result_carries_the_setup(dialog, monkeypatch):
    monkeypatch.setattr(dialog.dialog, "run", lambda: Gtk.ResponseType.OK)
    monkeypatch.setattr(dialog, "_fade_in_dialog", lambda o: None)
    result = dialog.run()
    assert (result["model"], result["device"], result["dictation_language"]) == \
        ("parakeet-v3", "vulkan", "en")
    assert "download_cuda" not in result and "use_vulkan" not in result


def test_first_run_never_mentions_cuda():
    assert "_build_cuda_option" not in SRC
    assert "Download CUDA Libraries" not in SRC


def test_options_button_says_what_can_be_changed(dialog):
    """A plain "Other options" expander went unnoticed, and a small "change"
    link on the card was easy to miss too. One button names the choices."""
    title = dialog.options_expander.get_label_widget().get_label()
    assert title == "Change language, model or graphics card"
    assert dialog.options_expander.get_style_context().has_class("tt-options")
    assert "<a href" not in dialog.rec_explanation.get_label()
    assert not dialog.options_expander.get_expanded()


def _find_button(widget, label):
    if isinstance(widget, Gtk.Button) and widget.get_label() == label:
        return widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            found = _find_button(child, label)
            if found:
                return found
    return None


def test_set_it_up_is_pinned_outside_the_scroll(dialog):
    """Inside the scrolling area, KDE's title bar left "Set it up" flush with
    the window's bottom edge until the user scrolled. Pinned below it, the
    button is always on screen whole."""
    button = _find_button(dialog.dialog, "Set it up")
    assert button is not None
    assert button.get_ancestor(Gtk.ScrolledWindow) is None


def test_flatpak_footer_no_longer_promises_a_model_choice():
    """The model is chosen on this screen now; the later picker is gone."""
    assert "choose your speech model" not in SRC
    assert "downloads your speech model, then starts" in SRC


def test_no_pulse_timer_without_anything_to_pulse(dialog, monkeypatch):
    """With no extension checkbox and no Flatpak warning the pulse timer
    stopped itself at once, and closing the window then removed it again:
    GLib warned "Source ID … was not found" on every first run off GNOME."""
    started, removed = [], []
    monkeypatch.setattr(wd.GLib, "timeout_add", lambda *a: started.append(a) or 7)
    monkeypatch.setattr(wd.GLib, "source_remove", lambda sid: removed.append(sid))
    monkeypatch.setattr(dialog.dialog, "run", lambda: Gtk.ResponseType.OK)
    monkeypatch.setattr(dialog, "_fade_in_dialog", lambda o: None)
    assert dialog._pulse_targets() == []
    dialog.run()
    assert not any(a[1] == dialog._pulse_checkboxes for a in started)
    assert removed == []

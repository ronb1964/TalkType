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


def test_change_link_opens_other_options_at_the_language(dialog):
    """Mockup A: "For English  change". The link was missing, so nothing on
    the card said the language could be changed."""
    assert '<a href="change">change</a>' in dialog.rec_explanation.get_label()
    assert not dialog.options_expander.get_expanded()
    handled = dialog.rec_explanation.emit("activate-link", "change")
    assert handled is True
    assert dialog.options_expander.get_expanded()

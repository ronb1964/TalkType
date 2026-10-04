"""First run on NVIDIA: the Full / Light choice is never greyed out.

The choice used to stay greyed out until "Use your NVIDIA graphics card" was
ticked, and Ron couldn't tell why Light couldn't be picked while testing
0.14.0. Clicking either choice now ticks the box.
"""
from types import SimpleNamespace

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


@pytest.fixture
def screen(monkeypatch):
    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    from talktype import welcome_dialog as wd, whisper_vulkan
    monkeypatch.setattr(whisper_vulkan, "vulkan_available", lambda: True)
    stub = SimpleNamespace(gpu_vulkan_radio=None)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    wd.WelcomeDialog._build_cuda_option(stub, box)
    radios = [w for w in _widgets(box) if isinstance(w, Gtk.RadioButton)]
    # Keep the box alive: when GTK destroys a container it disconnects its
    # children's signal handlers, which would make the clicks below do nothing.
    stub.keep_alive = box
    return stub, radios


def _widgets(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from _widgets(child)


def test_both_choices_can_be_clicked_before_the_box_is_ticked(screen):
    stub, radios = screen
    assert len(radios) == 2 and not stub.cuda_check.get_active()
    # is_sensitive() is the effective state, including a greyed-out parent box.
    assert all(r.is_sensitive() for r in radios)


def test_picking_light_ticks_the_box(screen):
    stub, radios = screen
    stub.gpu_vulkan_radio.clicked()
    assert stub.cuda_check.get_active() and stub.gpu_vulkan_radio.get_active()


def test_picking_full_ticks_the_box_even_though_it_was_already_selected(screen):
    """Full starts selected, so clicking it changes no selection; the box
    must still get ticked."""
    stub, radios = screen
    full = next(r for r in radios if r is not stub.gpu_vulkan_radio)
    full.clicked()
    assert stub.cuda_check.get_active() and full.get_active()

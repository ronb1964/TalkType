"""Backend selection is keyed on FLATPAK_ID: portals inside a Flatpak,
evdev+ydotool everywhere else."""
from talktype.output_backends import (
    get_output_backend, YdotoolOutputBackend, LibeiOutputBackend,
)
from talktype.input_backends import (
    get_input_backend, EvdevInputBackend, PortalInputBackend,
)


def test_output_backend_is_ydotool_without_flatpak():
    assert isinstance(get_output_backend(flatpak_id=""), YdotoolOutputBackend)


def test_output_backend_is_libei_in_flatpak():
    assert isinstance(
        get_output_backend(flatpak_id="io.github.ronb1964.TalkType"),
        LibeiOutputBackend,
    )


def test_input_backend_is_evdev_without_flatpak():
    assert isinstance(get_input_backend(flatpak_id=""), EvdevInputBackend)


def test_input_backend_is_portal_in_flatpak():
    assert isinstance(
        get_input_backend(flatpak_id="io.github.ronb1964.TalkType"),
        PortalInputBackend,
    )

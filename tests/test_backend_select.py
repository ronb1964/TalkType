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


class _Params:
    """Stands in for a GLib.Variant portal signal payload:
    (session_handle, shortcut_id, timestamp, options)."""

    def __init__(self, shortcut_id):
        self._shortcut_id = shortcut_id

    def unpack(self):
        return ("/session/handle", self._shortcut_id, 0, {})


class _Cfg:
    def __init__(self, mode):
        self.mode = mode


def test_portal_hold_mode_maps_press_and_release():
    from talktype import app
    b = PortalInputBackend(_Cfg("hold"))
    app._cmd_start_recording.clear()
    app._cmd_stop_recording.clear()
    b._on_activated(None, None, None, None, None, _Params("dictate"))
    assert app._cmd_start_recording.is_set()
    b._on_deactivated(None, None, None, None, None, _Params("dictate"))
    assert app._cmd_stop_recording.is_set()


def test_portal_toggle_mode_flips_on_press():
    from talktype import app
    b = PortalInputBackend(_Cfg("toggle"))
    app._cmd_start_recording.clear()
    app._cmd_stop_recording.clear()
    b._recording = False
    b._on_activated(None, None, None, None, None, _Params("dictate"))  # first press starts
    assert app._cmd_start_recording.is_set()
    app._cmd_start_recording.clear()
    b._on_activated(None, None, None, None, None, _Params("dictate"))  # second press stops
    assert app._cmd_stop_recording.is_set()


def test_portal_ignores_other_shortcut_ids():
    from talktype import app
    b = PortalInputBackend(_Cfg("hold"))
    app._cmd_start_recording.clear()
    b._on_activated(None, None, None, None, None, _Params("something-else"))
    assert not app._cmd_start_recording.is_set()

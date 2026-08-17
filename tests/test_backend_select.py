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
    def __init__(self, mode="hold"):
        self.mode = mode


def test_portal_hold_shortcut_maps_press_and_release():
    """dictate_hold = push-to-talk: press starts, release stops (like Backend A F8)."""
    from talktype import app
    b = PortalInputBackend(_Cfg())
    app._cmd_start_recording.clear()
    app._cmd_stop_recording.clear()
    b._on_activated(None, None, None, None, None, _Params("dictate_hold"))
    assert app._cmd_start_recording.is_set()
    b._on_deactivated(None, None, None, None, None, _Params("dictate_hold"))
    assert app._cmd_stop_recording.is_set()


def test_portal_toggle_shortcut_flips_on_press_and_ignores_release():
    """dictate_toggle = tap on/off (like Backend A F9): each press flips, release ignored."""
    from talktype import app
    b = PortalInputBackend(_Cfg())
    app._cmd_start_recording.clear()
    app._cmd_stop_recording.clear()
    b._recording = False
    b._on_activated(None, None, None, None, None, _Params("dictate_toggle"))  # start
    assert app._cmd_start_recording.is_set()
    app._cmd_start_recording.clear()
    b._on_deactivated(None, None, None, None, None, _Params("dictate_toggle"))  # ignored
    assert not app._cmd_stop_recording.is_set()
    b._on_activated(None, None, None, None, None, _Params("dictate_toggle"))  # stop
    assert app._cmd_stop_recording.is_set()


def test_portal_hold_and_toggle_are_both_live():
    """Both shortcuts work regardless of cfg.mode — parity with Backend A, where
    F8 (hold) and F9 (toggle) are always active at the same time."""
    from talktype import app
    b = PortalInputBackend(_Cfg("toggle"))  # mode must not gate either key
    app._cmd_start_recording.clear()
    b._on_activated(None, None, None, None, None, _Params("dictate_hold"))
    assert app._cmd_start_recording.is_set()


def test_portal_ignores_other_shortcut_ids():
    from talktype import app
    b = PortalInputBackend(_Cfg())
    app._cmd_start_recording.clear()
    b._on_activated(None, None, None, None, None, _Params("something-else"))
    assert not app._cmd_start_recording.is_set()

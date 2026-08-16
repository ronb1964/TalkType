"""Hotkey/input backends.

TalkType starts and stops recording from a global hotkey. Outside a Flatpak it
reads the key directly with evdev (Backend A); inside a Flatpak that is blocked,
so it registers a shortcut with the GlobalShortcuts portal and reacts to the
desktop's press/release signals (Backend B). Both backends drive the SAME
thread-safe events in app.py (_cmd_start_recording / _cmd_stop_recording), so the
recording core is identical either way. Chosen once at startup by FLATPAK_ID.
"""
import os


class InputBackend:
    """Listens for the dictate hotkey and drives recording start/stop.
    start() blocks (it runs the service's input loop); stop() is best-effort."""

    def start(self):
        raise NotImplementedError

    def stop(self):
        pass


class EvdevInputBackend(InputBackend):
    """Backend A: the existing evdev loop, unchanged."""

    def __init__(self, cfg, input_device_idx):
        self.cfg = cfg
        self.input_device_idx = input_device_idx

    def start(self):
        from . import app
        app._loop_evdev(self.cfg, self.input_device_idx)


class PortalInputBackend(InputBackend):
    """Backend B: GlobalShortcuts portal (Flatpak)."""

    def __init__(self, cfg):
        self.cfg = cfg

    def start(self):
        raise NotImplementedError("implemented in BB-7")


def get_input_backend(flatpak_id=None, cfg=None, input_device_idx=None) -> InputBackend:
    """Pick the input backend. flatpak_id=None reads the real environment."""
    if flatpak_id is None:
        flatpak_id = os.environ.get("FLATPAK_ID", "")
    if flatpak_id:
        return PortalInputBackend(cfg)
    return EvdevInputBackend(cfg, input_device_idx)

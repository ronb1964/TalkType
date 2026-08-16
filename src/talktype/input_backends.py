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
    """Backend B: the GlobalShortcuts portal (Flatpak).

    Registers one "dictate" shortcut; the desktop assigns the key and sends
    Activated (press) / Deactivated (release) signals, which we translate into
    the same app._cmd_start_recording / app._cmd_stop_recording events the evdev
    loop sets. A GLib timeout runs the shared app._service_tick so the recording
    core and auto-timeout work identically."""

    IFACE = "org.freedesktop.portal.GlobalShortcuts"

    def __init__(self, cfg, input_device_idx=None):
        self.cfg = cfg
        self.input_device_idx = input_device_idx
        self._recording = False  # toggle-mode state

    def _shortcut_id(self, params):
        try:
            return params.unpack()[1]
        except Exception:
            return None

    def _on_activated(self, conn, sender, path, iface, signal, params):
        if self._shortcut_id(params) != "dictate":
            return
        from . import app
        if getattr(self.cfg, "mode", "hold") == "hold":
            app._cmd_start_recording.set()
        else:  # tap-to-toggle: flip on each press, ignore release
            self._recording = not self._recording
            (app._cmd_start_recording if self._recording
             else app._cmd_stop_recording).set()

    def _on_deactivated(self, conn, sender, path, iface, signal, params):
        if self._shortcut_id(params) != "dictate":
            return
        from . import app
        if getattr(self.cfg, "mode", "hold") == "hold":
            app._cmd_stop_recording.set()
        # toggle mode ignores key release

    def _tick(self):
        from . import app
        app._service_tick(self.cfg, self.input_device_idx, self._svc)
        return True  # keep the GLib timer running

    def start(self):
        import logging
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
        from . import app, portal_common as pc
        logger = logging.getLogger(__name__)

        bus = pc.session_bus()
        loop = GLib.MainLoop()
        state = {"session": None}

        def create_session():
            def builder(token):
                opts = {"handle_token": GLib.Variant("s", token),
                        "session_handle_token": GLib.Variant("s", token + "_sess")}
                return GLib.Variant("(a{sv})", (opts,))
            pc.call_portal(bus, self.IFACE, "CreateSession", builder, on_session)

        def on_session(code, results):
            if code:
                logger.error("GlobalShortcuts CreateSession failed: %s", code)
                loop.quit()
                return
            state["session"] = results["session_handle"]
            bind()

        def bind():
            shortcuts = [("dictate",
                          {"description": GLib.Variant("s", "TalkType: dictate")})]

            def builder(token):
                opts = {"handle_token": GLib.Variant("s", token)}
                return GLib.Variant("(oa(sa{sv})sa{sv})",
                                    (state["session"], shortcuts, "", opts))
            pc.call_portal(bus, self.IFACE, "BindShortcuts", builder, on_bound)

        def on_bound(code, results):
            if code:
                logger.warning("BindShortcuts failed/cancelled (%s); the shortcut "
                               "may still be assignable in desktop settings", code)

        # sender=None: portal signals are proxied inside the sandbox.
        bus.signal_subscribe(None, self.IFACE, "Activated", None, None,
                             Gio.DBusSignalFlags.NONE, self._on_activated)
        bus.signal_subscribe(None, self.IFACE, "Deactivated", None, None,
                             Gio.DBusSignalFlags.NONE, self._on_deactivated)

        # Inside a Flatpak the app id is intrinsic; Registry is refused there.
        if not os.environ.get("FLATPAK_ID"):
            pc.register_app_id(bus)

        self._svc = app._ServiceState(self.cfg)
        GLib.timeout_add(50, self._tick)
        create_session()
        loop.run()


def get_input_backend(flatpak_id=None, cfg=None, input_device_idx=None) -> InputBackend:
    """Pick the input backend. flatpak_id=None reads the real environment."""
    if flatpak_id is None:
        flatpak_id = os.environ.get("FLATPAK_ID", "")
    if flatpak_id:
        return PortalInputBackend(cfg, input_device_idx)
    return EvdevInputBackend(cfg, input_device_idx)

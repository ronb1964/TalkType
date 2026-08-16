"""Text-injection backends.

TalkType needs to type transcribed text into whatever app is focused. Outside a
Flatpak it uses ydotool (Backend A); inside a Flatpak the uinput path is blocked,
so it types through the RemoteDesktop portal + libei (Backend B). The backend is
chosen once at startup by FLATPAK_ID and hidden behind a single method so the
recording core never knows which one is in use.
"""
import os


class OutputBackend:
    """Types text into the focused application. Returns True if the text was
    actually delivered, False if injection failed (never raises — the caller
    surfaces a plain-language notice on False)."""

    def type_text(self, text: str) -> bool:
        raise NotImplementedError


class YdotoolOutputBackend(OutputBackend):
    """Backend A: the existing ydotool path, unchanged."""

    def type_text(self, text: str) -> bool:
        from . import app
        return app._type_text(text)


class LibeiOutputBackend(OutputBackend):
    """Backend B: type via the RemoteDesktop portal + libei (Flatpak).

    Establishes one long-lived RemoteDesktop/EIS session (the user approves the
    "Allow remote control?" dialog once; a restore token remembers it), then
    streams keystrokes over it. type_text never raises — it returns False so the
    recording core surfaces its usual "couldn't type" notice."""

    IFACE = "org.freedesktop.portal.RemoteDesktop"
    KEYBOARD = 1  # RemoteDesktop DeviceType bitmask: KEYBOARD=1, POINTER=2

    def __init__(self):
        self._session = None  # libei_ctypes.LibeiSession once established

    def _token_path(self) -> str:
        import os
        from .config import get_data_dir
        return os.path.join(get_data_dir(), "remote_desktop_token")

    def _load_token(self) -> str:
        try:
            with open(self._token_path()) as f:
                return f.read().strip()
        except OSError:
            return ""

    def _save_token(self, token: str) -> None:
        import logging
        try:
            with open(self._token_path(), "w") as f:
                f.write(token or "")
        except OSError as e:
            logging.getLogger(__name__).debug("could not save restore token: %s", e)

    def ensure_session(self) -> bool:
        """Establish the RemoteDesktop/EIS session + libei context if needed.
        Returns True when a typing device is ready. Never raises."""
        import logging
        logger = logging.getLogger(__name__)
        if self._session is not None:
            return True
        try:
            fd = self._run_handshake()
        except Exception as e:
            logger.error("RemoteDesktop portal handshake failed: %s", e)
            return False
        if fd is None:
            logger.warning("RemoteDesktop portal did not yield an EIS fd "
                           "(permission denied?)")
            return False
        try:
            from . import libei_ctypes
            session = libei_ctypes.LibeiSession(fd)
            if not session.pump_until_ready():
                logger.warning("libei device did not become ready")
                return False
            self._session = session
            return True
        except Exception as e:
            logger.error("libei session setup failed: %s", e)
            return False

    def _run_handshake(self):
        """Drive CreateSession -> SelectDevices -> Start -> ConnectToEIS on a
        GLib loop; returns the EIS fd (int) or None. Uses a saved restore_token
        to skip the approval dialog on later launches."""
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
        from . import portal_common as pc

        bus = pc.session_bus()
        loop = GLib.MainLoop()
        st = {"session": None, "fd": None}

        def fail(code):
            st["fd"] = None
            loop.quit()

        def create_session():
            def b(token):
                opts = {"handle_token": GLib.Variant("s", token),
                        "session_handle_token": GLib.Variant("s", token + "_sess")}
                return GLib.Variant("(a{sv})", (opts,))
            pc.call_portal(bus, self.IFACE, "CreateSession", b, on_session)

        def on_session(code, results):
            if code:
                return fail(code)
            st["session"] = results["session_handle"]
            select_devices()

        def select_devices():
            def b(token):
                opts = {"handle_token": GLib.Variant("s", token),
                        "types": GLib.Variant("u", self.KEYBOARD),
                        "persist_mode": GLib.Variant("u", 2)}
                saved = self._load_token()
                if saved:
                    opts["restore_token"] = GLib.Variant("s", saved)
                return GLib.Variant("(oa{sv})", (st["session"], opts))
            pc.call_portal(bus, self.IFACE, "SelectDevices", b,
                           lambda c, r: start() if not c else fail(c))

        def start():
            def b(token):
                opts = {"handle_token": GLib.Variant("s", token)}
                return GLib.Variant("(osa{sv})", (st["session"], "", opts))
            pc.call_portal(bus, self.IFACE, "Start", b, on_start)

        def on_start(code, results):
            if code:
                return fail(code)
            token = results.get("restore_token")
            if token:
                self._save_token(token)
            connect_eis()

        def connect_eis():
            opts = GLib.Variant("(oa{sv})", (st["session"], {}))
            ret, fd_list = bus.call_with_unix_fd_list_sync(
                pc.BUS_NAME, pc.OBJ_PATH, self.IFACE, "ConnectToEIS", opts,
                GLib.VariantType("(h)"), Gio.DBusCallFlags.NONE, -1, None, None)
            st["fd"] = fd_list.get(ret.unpack()[0])
            loop.quit()

        create_session()
        loop.run()
        return st["fd"]

    def type_text(self, text: str) -> bool:
        import logging
        try:
            if not self.ensure_session():
                return False
            return bool(self._session.type_string(text))
        except Exception as e:
            logging.getLogger(__name__).error("libei type_text failed: %s", e)
            return False


def get_output_backend(flatpak_id=None) -> OutputBackend:
    """Pick the output backend. flatpak_id=None reads the real environment."""
    if flatpak_id is None:
        flatpak_id = os.environ.get("FLATPAK_ID", "")
    return LibeiOutputBackend() if flatpak_id else YdotoolOutputBackend()

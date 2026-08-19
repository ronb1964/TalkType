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
    surfaces a plain-language notice on False).

    Beyond plain text, editing voice commands need to press key combos —
    'delete everything' (Ctrl+A + Backspace) and character-undo (Backspace ×N).
    Those go through the backend too, so the Flatpak (libei) and host (ydotool)
    paths stay in lockstep instead of the commands hardcoding ydotool and
    silently doing nothing inside the sandbox."""

    def type_text(self, text: str) -> bool:
        raise NotImplementedError

    def select_all_delete(self) -> bool:
        """Clear the focused field (Ctrl+A + Backspace)."""
        raise NotImplementedError

    def backspaces(self, count: int) -> bool:
        """Send `count` Backspace presses (character-level undo)."""
        raise NotImplementedError


class YdotoolOutputBackend(OutputBackend):
    """Backend A: the existing ydotool path, unchanged."""

    def type_text(self, text: str) -> bool:
        from . import app
        return app._type_text(text)

    def select_all_delete(self) -> bool:
        from . import app
        return app._send_select_all_delete()

    def backspaces(self, count: int) -> bool:
        from . import app
        return app._send_backspaces(count)


class LibeiOutputBackend(OutputBackend):
    """Backend B: type via the RemoteDesktop portal + libei (Flatpak).

    Establishes one long-lived RemoteDesktop/EIS session (the user approves the
    "Allow remote control?" dialog once; a restore token remembers it), then
    streams keystrokes over it. type_text never raises — it returns False so the
    recording core surfaces its usual "couldn't type" notice."""

    IFACE = "org.freedesktop.portal.RemoteDesktop"
    KEYBOARD = 1  # RemoteDesktop DeviceType bitmask: KEYBOARD=1, POINTER=2

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
        import os
        path = self._token_path()
        try:
            # Create data/TalkType/ if it doesn't exist yet. On a fresh CPU-only
            # Flatpak install nothing else has written there (no CUDA libs, and
            # the first-run flag may land elsewhere), so without this the write
            # fails silently, the restore token never persists, and GNOME
            # re-prompts "Allow remote interaction?" on every dictation. Mirrors
            # mark_first_run_complete() and save_config().
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(token or "")
        except OSError as e:
            logging.getLogger(__name__).debug("could not save restore token: %s", e)

    def _close_session(self, session_path):
        """Close a RemoteDesktop portal session (one is created per dictation)."""
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio
        from . import portal_common as pc
        try:
            pc.session_bus().call_sync(
                pc.BUS_NAME, session_path, "org.freedesktop.portal.Session",
                "Close", None, None, Gio.DBusCallFlags.NONE, 2000, None)
        except Exception:
            pass

    def _run_handshake(self):
        """Drive CreateSession -> SelectDevices -> Start -> ConnectToEIS on a
        GLib loop; returns (EIS fd or None, session handle path). Uses a saved
        restore_token to skip the approval dialog after the first time."""
        import gi
        import logging
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
        from . import portal_common as pc

        logger = logging.getLogger(__name__)
        # Own GMainContext: the per-dictation handshake now runs on a worker
        # thread (Backend B moved transcription + typing off the hotkey loop).
        # Two threads may not iterate the same (default) context, so push a
        # private one — the portal's async callbacks are then delivered on it.
        ctx = GLib.MainContext.new()
        ctx.push_thread_default()
        bus = pc.session_bus()
        loop = GLib.MainLoop.new(ctx, False)
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
                logger.info("RemoteDesktop session persisted (restore token saved)")
            else:
                # No token means the desktop won't restore this grant, so the
                # approval dialog reappears next dictation. Surface it plainly so
                # a re-prompt loop is diagnosable from the log alone.
                logger.warning("RemoteDesktop Start returned no restore_token; "
                               "the desktop will re-prompt on the next dictation")
            connect_eis()

        def connect_eis():
            opts = GLib.Variant("(oa{sv})", (st["session"], {}))
            ret, fd_list = bus.call_with_unix_fd_list_sync(
                pc.BUS_NAME, pc.OBJ_PATH, self.IFACE, "ConnectToEIS", opts,
                GLib.VariantType("(h)"), Gio.DBusCallFlags.NONE, -1, None, None)
            st["fd"] = fd_list.get(ret.unpack()[0])
            loop.quit()

        try:
            create_session()
            loop.run()
            return st["fd"], st["session"]
        finally:
            ctx.pop_thread_default()

    def _with_session(self, action) -> bool:
        """Run `action(session)` inside a FRESH RemoteDesktop/EIS session. A
        persistent session only ever types once — KDE's EIS delivers keystrokes
        on a fresh DEVICE_RESUMED, so re-establishing per call is what emits
        reliably (proven by the portal spike). The saved restore_token means the
        approval dialog appears only the first time. Returns action's bool result,
        or False if the handshake/device wasn't ready. Never raises."""
        import logging
        import os
        logger = logging.getLogger(__name__)
        fd = None
        session_path = None
        try:
            fd, session_path = self._run_handshake()
            if fd is None:
                logger.warning("RemoteDesktop portal did not yield an EIS fd "
                               "(permission denied?)")
                return False
            from . import libei_ctypes
            session = libei_ctypes.LibeiSession(fd)
            if not session.pump_until_ready():
                logger.warning("libei device did not become ready")
                return False
            return bool(action(session))
        except Exception as e:
            logger.error("libei session action failed: %s", e)
            return False
        finally:
            if session_path:
                self._close_session(session_path)
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def type_text(self, text: str) -> bool:
        return self._with_session(lambda s: s.type_string(text))

    def select_all_delete(self) -> bool:
        return self._with_session(lambda s: s.select_all_delete())

    def backspaces(self, count: int) -> bool:
        return self._with_session(lambda s: s.backspaces(count))


def get_output_backend(flatpak_id=None) -> OutputBackend:
    """Pick the output backend. flatpak_id=None reads the real environment."""
    if flatpak_id is None:
        flatpak_id = os.environ.get("FLATPAK_ID", "")
    return LibeiOutputBackend() if flatpak_id else YdotoolOutputBackend()

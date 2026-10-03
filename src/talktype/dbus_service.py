#!/usr/bin/env python3
"""
D-Bus service for TalkType - enables GNOME extension integration
"""

from gi.repository import GLib
import dbus
import dbus.service
import dbus.mainloop.glib

from .logger import setup_logger

logger = setup_logger(__name__)


# Cache of the currently focused window's wm_class, pushed from the GNOME
# extension whenever focus changes. Read by app._paste_text to decide between
# plain Ctrl+V (regular apps) and Ctrl+Shift+V (terminals).
_focused_window_class: str | None = None

# The bus identifiers, at module level so providers that fill the focused-window
# cache (the GNOME extension's Python side, and kwin_focus on KDE) can name the
# same service without a second copy of these strings.
DBUS_NAME = "io.github.ronb1964.TalkType"
DBUS_PATH = "/io/github/ronb1964/TalkType"
DBUS_INTERFACE = "io.github.ronb1964.TalkType"


def get_focused_window_class() -> str | None:
    """Return the wm_class of the currently focused window, or None if unknown.

    NOTE: This reads the in-memory cache local to *this* process. It only works
    inside the tray process, where the D-Bus service receives push updates.
    The dictation engine (talktype.app) runs in a separate subprocess and must
    query via D-Bus instead — see _query_focused_window_class() in app.py.
    """
    return _focused_window_class


class TalkTypeDBusService(dbus.service.Object):
    """
    D-Bus service interface for TalkType

    Bus Name: io.github.ronb1964.TalkType
    Object Path: /io/github/ronb1964/TalkType
    Interface: io.github.ronb1964.TalkType
    """

    # Module-level constants above are the single definition; these keep the
    # long-standing TalkTypeDBusService.DBUS_* attribute names working.
    DBUS_NAME = DBUS_NAME
    DBUS_PATH = DBUS_PATH
    DBUS_INTERFACE = DBUS_INTERFACE

    def __init__(self, app_instance, primary=True):
        """Initialize D-Bus service with reference to app instance.

        *primary* is True for the tray, which owns the bus name: the GNOME
        extension talks to it, and the dictation service reports recording
        state to it over D-Bus. The dictation service registers too
        (primary=False), only as a stand-in for when no tray is running.

        Both used to request the name the same way, so the second one queued
        behind the first. When the tray restarted while the service kept
        running, the queued service inherited the name: the extension's menu
        actions reached a stub that didn't know newer methods
        (FixWordInDictation failed as "unknown method"), and the service's
        recording-state reports went to itself instead of the tray.

        Now the tray always takes the name, from a stand-in service too, and
        the service never queues for it, so it can't inherit it. If the tray
        already has the name, the service gets NameExistsException.
        """
        self.app = app_instance

        # Set up D-Bus main loop
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

        # Get session bus
        self.bus = dbus.SessionBus()

        if primary:
            self.bus_name = dbus.service.BusName(
                self.DBUS_NAME, bus=self.bus, replace_existing=True)
        else:
            self.bus_name = dbus.service.BusName(
                self.DBUS_NAME, bus=self.bus, allow_replacement=True, do_not_queue=True)

        # Initialize parent
        super().__init__(self.bus_name, self.DBUS_PATH)

        if self.owns_name():
            logger.info(f"D-Bus service started: {self.DBUS_NAME}")
        else:
            # Only possible for the tray, behind something that won't let go
            # of the name (a TalkType older than this fix).
            logger.warning(f"D-Bus name {self.DBUS_NAME} is held by another process; "
                           "waiting in line for it")

    def owns_name(self):
        """Whether this process currently owns the TalkType bus name."""
        try:
            return self.bus.get_name_owner(self.DBUS_NAME) == self.bus.get_unique_name()
        except Exception:
            return False

    # ==================== Internal Helpers ====================

    def _dispatch(self, method_name, *args):
        """Dispatch a D-Bus method call to the app instance via GLib main loop.

        All D-Bus action methods follow the same pattern: log the call,
        check if the app has the method, then schedule it on the main loop.
        This helper eliminates that repetition.
        """
        logger.debug(f"D-Bus: {method_name} called" +
                      (f" with {args}" if args else ""))
        if hasattr(self.app, method_name):
            GLib.idle_add(getattr(self.app, method_name), *args)

    # ==================== Properties ====================

    @dbus.service.method(DBUS_INTERFACE, out_signature='b')
    def IsRecording(self):
        """Check if currently recording"""
        return self.app.is_recording if hasattr(self.app, 'is_recording') else False

    @dbus.service.method(DBUS_INTERFACE, out_signature='b')
    def IsServiceRunning(self):
        """Check if the dictation service is running"""
        return self.app.service_running if hasattr(self.app, 'service_running') else False

    @dbus.service.method(DBUS_INTERFACE, out_signature='s')
    def GetCurrentModel(self):
        """Get the current Whisper model name"""
        if hasattr(self.app, 'config'):
            return str(getattr(self.app.config, 'model', 'large-v3'))
        return 'unknown'

    @dbus.service.method(DBUS_INTERFACE, out_signature='s')
    def GetDeviceType(self):
        """Get the device the model really runs on (cpu/cuda). This is what
        the GNOME extension's Device line shows, so it matches the tray."""
        if hasattr(self.app, 'config'):
            from .parakeet_engine import effective_device
            cfg = self.app.config
            return str(effective_device(getattr(cfg, 'model', ''), getattr(cfg, 'device', 'cpu')))
        return 'cpu'

    @dbus.service.method(DBUS_INTERFACE, out_signature='a{sv}')
    def GetStatus(self):
        """Get comprehensive status information"""
        status = {
            'recording': self.IsRecording(),
            'service_running': self.IsServiceRunning(),
            'model': self.GetCurrentModel(),
            'device': self.GetDeviceType(),
            'injection_mode': self.GetInjectionMode(),
        }

        # The auto-timeout is the ONLY thing separating the "Battery Saver" and
        # "Fastest" presets — both are tiny/CPU. Without it here, the GNOME
        # extension cannot tell which one is active and always reports Fastest.
        # Adding keys to this dict is backward-compatible: older extensions
        # ignore what they do not read.
        if hasattr(self.app, 'config'):
            status['auto_timeout_enabled'] = bool(
                getattr(self.app.config, 'auto_timeout_enabled', False))
            status['auto_timeout_minutes'] = int(
                getattr(self.app.config, 'auto_timeout_minutes', 0))

        # Add statistics if available
        if hasattr(self.app, 'stats'):
            status['stats'] = {
                'words': self.app.stats.get('words', 0),
                'sessions': self.app.stats.get('sessions', 0),
            }

        return status

    # ==================== Actions ====================

    @dbus.service.method(DBUS_INTERFACE)
    def StartRecording(self):
        """Start recording (hold mode)"""
        self._dispatch('start_recording')

    @dbus.service.method(DBUS_INTERFACE)
    def StopRecording(self):
        """Stop recording"""
        self._dispatch('stop_recording')

    @dbus.service.method(DBUS_INTERFACE)
    def ToggleRecording(self):
        """Toggle recording on/off"""
        self._dispatch('toggle_recording')

    @dbus.service.method(DBUS_INTERFACE)
    def StartService(self):
        """Start the dictation service"""
        self._dispatch('start_service')

    @dbus.service.method(DBUS_INTERFACE)
    def StopService(self):
        """Stop the dictation service"""
        self._dispatch('stop_service')

    @dbus.service.method(DBUS_INTERFACE)
    def RestartService(self):
        """Restart the dictation service"""
        self._dispatch('restart_service')

    @dbus.service.method(DBUS_INTERFACE, in_signature='s')
    def SetModel(self, model_name: str):
        """Change the Whisper model"""
        self._dispatch('set_model', model_name)

    @dbus.service.method(DBUS_INTERFACE, out_signature='s')
    def GetInjectionMode(self):
        """Get current text injection mode (auto/paste/type)"""
        if hasattr(self.app, 'config'):
            return str(getattr(self.app.config, 'injection_mode', 'auto'))
        return 'auto'

    @dbus.service.method(DBUS_INTERFACE, in_signature='s')
    def SetInjectionMode(self, mode: str):
        """Change the text injection mode"""
        self._dispatch('set_injection_mode', mode)

    @dbus.service.method(DBUS_INTERFACE, in_signature='s')
    def SetFocusedWindowClass(self, wm_class: str):
        """Receive the focused window's wm_class from the GNOME extension.

        Called on every focus change. Cached for cross-process query via
        GetFocusedWindowClass — the dictation engine runs in a separate
        subprocess from this service.
        """
        global _focused_window_class
        new_class = wm_class if wm_class else None
        if new_class != _focused_window_class:
            logger.info(f"Focused window class: {new_class!r}")
        _focused_window_class = new_class

    @dbus.service.method(DBUS_INTERFACE, out_signature='s')
    def GetFocusedWindowClass(self):
        """Return the currently focused window's wm_class (empty string if unknown).

        Used by the dictation engine subprocess (talktype.app) to read the cache
        that the GNOME extension pushes into this tray-side service.
        """
        return _focused_window_class or ''

    @dbus.service.method(DBUS_INTERFACE, in_signature='s')
    def ApplyPerformancePreset(self, preset: str):
        """Apply a performance preset (fastest/balanced/accurate/battery)"""
        self._dispatch('set_performance_preset', preset)

    @dbus.service.method(DBUS_INTERFACE, out_signature='as')
    def GetRecentDictations(self):
        """Recent dictations, newest first (see history.py).

        Read straight from the history file rather than dispatched to the app:
        it is a quick file read, and the caller needs the answer back.
        """
        from .history import get_entries
        return get_entries()

    @dbus.service.method(DBUS_INTERFACE)
    def ClearRecentDictations(self):
        """Forget every recent dictation."""
        from .history import clear
        clear()

    @dbus.service.method(DBUS_INTERFACE)
    def FixWordInDictation(self):
        """Open the Fix a Word window on the newest recent dictation."""
        self._dispatch('show_fix_word')

    @dbus.service.method(DBUS_INTERFACE)
    def OpenPreferences(self):
        """Open the preferences window"""
        self._dispatch('show_preferences')

    @dbus.service.method(DBUS_INTERFACE)
    def OpenPreferencesUpdates(self):
        """Open the preferences window directly to the Updates tab"""
        self._dispatch('show_preferences_updates')

    @dbus.service.method(DBUS_INTERFACE)
    def ShowHelp(self):
        """Show the help dialog"""
        self._dispatch('show_help')

    @dbus.service.method(DBUS_INTERFACE)
    def ShowVoiceCommands(self):
        """Show the voice commands quick reference popup"""
        self._dispatch('show_voice_commands')

    @dbus.service.method(DBUS_INTERFACE)
    def ShowAbout(self):
        """Show the about dialog"""
        self._dispatch('show_about')

    @dbus.service.method(DBUS_INTERFACE)
    def Quit(self):
        """Quit the application"""
        self._dispatch('quit')

    @dbus.service.method(DBUS_INTERFACE, in_signature='b')
    def NotifyRecordingState(self, is_recording: bool):
        """
        Called by the dictation engine (app.py) to report recording state changes.
        The tray owns the D-Bus name, so only it can emit signals that the
        GNOME extension will receive. App.py calls this method to relay the state.
        """
        logger.debug(f"D-Bus: NotifyRecordingState called: {is_recording}")
        self.app.is_recording = is_recording
        self.RecordingStateChanged(is_recording)

    @dbus.service.method(DBUS_INTERFACE, in_signature='s')
    def NotifyHotkeyPressed(self, key_name: str):
        """
        Called by app.py when a hotkey is pressed during test mode.
        The tray owns the D-Bus name, so only it can emit signals that
        the prefs dialog will receive. key_name is 'hold' or 'toggle'.
        """
        logger.debug(f"D-Bus: NotifyHotkeyPressed called: {key_name}")
        self.HotkeyPressed(key_name)

    @dbus.service.method(DBUS_INTERFACE)
    def CheckForUpdates(self):
        """
        Check for updates asynchronously.
        Results are sent via UpdateCheckComplete signal.
        """
        logger.debug("D-Bus: CheckForUpdates called")
        import threading

        def do_check():
            try:
                from . import update_checker
                result = update_checker.check_for_updates()

                # Show a PERSISTENT result window via the app — a dialog the user
                # dismisses with OK — instead of relying on the extension's fleeting
                # GNOME notification (easy to miss). Only the manual, extension-triggered
                # check reaches this D-Bus method; the background auto-check does not.
                if result.get("success") and hasattr(self.app, "show_update_result"):
                    self.app.show_update_result(result)

                # Also emit the signal so the extension can update its own state/icon.
                GLib.idle_add(
                    self.UpdateCheckComplete,
                    result.get("success", False),
                    result.get("current_version", "unknown"),
                    result.get("latest_version", "unknown"),
                    result.get("update_available", False),
                    result.get("extension_current", -1) if result.get("extension_current") else -1,
                    result.get("extension_latest", -1) if result.get("extension_latest") else -1,
                    result.get("extension_update", False),
                    result.get("release", {}).get("html_url", "") if result.get("release") else "",
                    result.get("error", "") if result.get("error") else ""
                )
            except Exception as e:
                logger.error(f"CheckForUpdates error: {e}")
                GLib.idle_add(
                    self.UpdateCheckComplete,
                    False, "unknown", "unknown", False, -1, -1, False, "", str(e)
                )

        thread = threading.Thread(target=do_check, daemon=True)
        thread.start()

    # ==================== Signals ====================

    @dbus.service.signal(DBUS_INTERFACE, signature='b')
    def RecordingStateChanged(self, is_recording: bool):
        """Emitted when recording state changes"""
        pass

    @dbus.service.signal(DBUS_INTERFACE, signature='b')
    def ServiceStateChanged(self, is_running: bool):
        """Emitted when service state changes"""
        pass

    @dbus.service.signal(DBUS_INTERFACE, signature='s')
    def TranscriptionComplete(self, text: str):
        """Emitted when a transcription is completed"""
        pass

    @dbus.service.signal(DBUS_INTERFACE, signature='s')
    def ModelChanged(self, model_name: str):
        """Emitted when the model is changed"""
        pass

    @dbus.service.signal(DBUS_INTERFACE, signature='s')
    def InjectionModeChanged(self, mode: str):
        """Emitted when injection mode changes (auto/paste/type)"""
        pass

    @dbus.service.signal(DBUS_INTERFACE, signature='ss')
    def ErrorOccurred(self, error_type: str, message: str):
        """Emitted when an error occurs"""
        pass

    @dbus.service.signal(DBUS_INTERFACE, signature='s')
    def HotkeyPressed(self, key_name: str):
        """Emitted when a hotkey is pressed during test mode (PauseHotkeys).
        key_name is 'hold' or 'toggle'."""
        pass

    @dbus.service.signal(DBUS_INTERFACE, signature='bssbiibss')
    def UpdateCheckComplete(self, success: bool, current_version: str,
                           latest_version: str, update_available: bool,
                           extension_current: int, extension_latest: int,
                           extension_update: bool, release_url: str, error: str):
        """
        Emitted when update check completes.

        Args:
            success: True if check succeeded
            current_version: Current AppImage version
            latest_version: Latest available version
            update_available: True if AppImage update available
            extension_current: Installed extension version (-1 if not installed)
            extension_latest: Latest extension version (-1 if unknown)
            extension_update: True if extension update available
            release_url: URL to release page on GitHub
            error: Error message if check failed
        """
        pass

    # ==================== Helper Methods ====================

    def emit_recording_state(self, is_recording: bool):
        """Emit recording state change signal"""
        self.RecordingStateChanged(is_recording)

    def emit_service_state(self, is_running: bool):
        """Emit service state change signal"""
        self.ServiceStateChanged(is_running)

    def emit_transcription(self, text: str):
        """Emit transcription complete signal"""
        self.TranscriptionComplete(text)

    def emit_model_changed(self, model_name: str):
        """Emit model changed signal"""
        self.ModelChanged(model_name)

    def emit_injection_mode_changed(self, mode: str):
        """Emit injection mode changed signal"""
        self.InjectionModeChanged(mode)

    def emit_error(self, error_type: str, message: str):
        """Emit error signal"""
        self.ErrorOccurred(error_type, message)

    def emit_hotkey_pressed(self, key_name: str):
        """Emit hotkey pressed signal (during test mode)"""
        self.HotkeyPressed(key_name)

#!/usr/bin/env python3
"""
D-Bus service for TalkType - enables GNOME extension integration
"""

from gi.repository import GLib
import dbus
import dbus.service
import dbus.mainloop.glib
from typing import Optional, Callable


class TalkTypeDBusService(dbus.service.Object):
    """
    D-Bus service interface for TalkType

    Bus Name: io.github.ronb1964.TalkType
    Object Path: /io/github/ronb1964/TalkType
    Interface: io.github.ronb1964.TalkType
    """

    DBUS_NAME = "io.github.ronb1964.TalkType"
    DBUS_PATH = "/io/github/ronb1964/TalkType"
    DBUS_INTERFACE = "io.github.ronb1964.TalkType"

    def __init__(self, app_instance):
        """Initialize D-Bus service with reference to app instance"""
        self.app = app_instance

        # Set up D-Bus main loop
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

        # Get session bus
        self.bus = dbus.SessionBus()

        # Request bus name
        self.bus_name = dbus.service.BusName(self.DBUS_NAME, bus=self.bus)

        # Initialize parent
        super().__init__(self.bus_name, self.DBUS_PATH)

        print(f"✅ D-Bus service started: {self.DBUS_NAME}")

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
        """Get current device type (cpu/cuda)"""
        if hasattr(self.app, 'config'):
            return str(getattr(self.app.config, 'device', 'cpu'))
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
        print("D-Bus: StartRecording called")
        if hasattr(self.app, 'start_recording'):
            GLib.idle_add(self.app.start_recording)

    @dbus.service.method(DBUS_INTERFACE)
    def StopRecording(self):
        """Stop recording"""
        print("D-Bus: StopRecording called")
        if hasattr(self.app, 'stop_recording'):
            GLib.idle_add(self.app.stop_recording)

    @dbus.service.method(DBUS_INTERFACE)
    def ToggleRecording(self):
        """Toggle recording on/off"""
        print("D-Bus: ToggleRecording called")
        if hasattr(self.app, 'toggle_recording'):
            GLib.idle_add(self.app.toggle_recording)

    @dbus.service.method(DBUS_INTERFACE)
    def StartService(self):
        """Start the dictation service"""
        print("D-Bus: StartService called")
        if hasattr(self.app, 'start_service'):
            GLib.idle_add(self.app.start_service)

    @dbus.service.method(DBUS_INTERFACE)
    def StopService(self):
        """Stop the dictation service"""
        print("D-Bus: StopService called")
        if hasattr(self.app, 'stop_service'):
            GLib.idle_add(self.app.stop_service)

    @dbus.service.method(DBUS_INTERFACE, in_signature='s')
    def SetModel(self, model_name: str):
        """Change the Whisper model"""
        print(f"D-Bus: SetModel called with {model_name}")
        if hasattr(self.app, 'set_model'):
            GLib.idle_add(self.app.set_model, model_name)

    @dbus.service.method(DBUS_INTERFACE, out_signature='s')
    def GetInjectionMode(self):
        """Get current text injection mode (auto/paste/type)"""
        if hasattr(self.app, 'config'):
            return str(getattr(self.app.config, 'injection_mode', 'auto'))
        return 'auto'

    @dbus.service.method(DBUS_INTERFACE, in_signature='s')
    def SetInjectionMode(self, mode: str):
        """Change the text injection mode"""
        print(f"D-Bus: SetInjectionMode called with {mode}")
        if hasattr(self.app, 'set_injection_mode'):
            GLib.idle_add(self.app.set_injection_mode, mode)

    @dbus.service.method(DBUS_INTERFACE, in_signature='s')
    def ApplyPerformancePreset(self, preset: str):
        """Apply a performance preset (fastest/balanced/accurate/battery)"""
        print(f"D-Bus: ApplyPerformancePreset called with {preset}")
        if hasattr(self.app, 'set_performance_preset'):
            GLib.idle_add(self.app.set_performance_preset, preset)

    @dbus.service.method(DBUS_INTERFACE)
    def OpenPreferences(self):
        """Open the preferences window"""
        print("D-Bus: OpenPreferences called")
        if hasattr(self.app, 'show_preferences'):
            GLib.idle_add(self.app.show_preferences)

    @dbus.service.method(DBUS_INTERFACE)
    def OpenPreferencesUpdates(self):
        """Open the preferences window directly to the Updates tab"""
        print("D-Bus: OpenPreferencesUpdates called")
        if hasattr(self.app, 'show_preferences_updates'):
            GLib.idle_add(self.app.show_preferences_updates)

    @dbus.service.method(DBUS_INTERFACE)
    def ShowHelp(self):
        """Show the help dialog"""
        print("D-Bus: ShowHelp called")
        if hasattr(self.app, 'show_help'):
            GLib.idle_add(self.app.show_help)

    @dbus.service.method(DBUS_INTERFACE)
    def ShowAbout(self):
        """Show the about dialog"""
        print("D-Bus: ShowAbout called")
        if hasattr(self.app, 'show_about'):
            GLib.idle_add(self.app.show_about)

    @dbus.service.method(DBUS_INTERFACE)
    def Quit(self):
        """Quit the application"""
        print("D-Bus: Quit called")
        if hasattr(self.app, 'quit'):
            GLib.idle_add(self.app.quit)

    @dbus.service.method(DBUS_INTERFACE)
    def CheckForUpdates(self):
        """
        Check for updates asynchronously.
        Results are sent via UpdateCheckComplete signal.
        """
        print("D-Bus: CheckForUpdates called")
        import threading

        def do_check():
            try:
                from . import update_checker
                result = update_checker.check_for_updates()

                # Send signal with results
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
                print(f"D-Bus: CheckForUpdates error: {e}")
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

    @dbus.service.signal(DBUS_INTERFACE, signature='ss')
    def ErrorOccurred(self, error_type: str, message: str):
        """Emitted when an error occurs"""
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

    def emit_error(self, error_type: str, message: str):
        """Emit error signal"""
        self.ErrorOccurred(error_type, message)


def test_dbus_service():
    """Test D-Bus service standalone"""

    class MockApp:
        """Mock app for testing"""
        is_recording = False
        service_running = True
        config = {'model_size': 'large-v3', 'device': 'cuda'}

        def start_recording(self):
            print("Mock: start_recording called")
            self.is_recording = True

        def stop_recording(self):
            print("Mock: stop_recording called")
            self.is_recording = False

    print("Testing D-Bus service...")
    app = MockApp()
    service = TalkTypeDBusService(app)

    print("\nD-Bus service ready. Testing with dbus-send:")
    print(f"  dbus-send --session --print-reply --dest={TalkTypeDBusService.DBUS_NAME} {TalkTypeDBusService.DBUS_PATH} {TalkTypeDBusService.DBUS_INTERFACE}.GetStatus")

    # Run main loop
    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    test_dbus_service()

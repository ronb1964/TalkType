import os
import signal
# CRITICAL: Disable HuggingFace XET downloads BEFORE any imports
# XET bypasses tqdm_class progress tracking, breaking our download progress UI
os.environ["HF_HUB_DISABLE_XET"] = "1"

import gi
gi.require_version("Gtk", "3.0")
# Ayatana is the maintained successor to the dead libappindicator project, and
# it is what build-deb.sh and build-rpm.sh actually declare as a dependency.
# The old "AppIndicator3" typelib references libappindicator3.so.1, a library
# Debian/Ubuntu still provide as a compat shim but Fedora does not ship at all —
# so bundling the old typelib crashed the tray on launch on Fedora. Imported
# under the historical name to keep the call sites below unchanged.
gi.require_version("AyatanaAppIndicator3", "0.1")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib
from gi.repository import AyatanaAppIndicator3 as AppIndicator3
import subprocess
import time
import sys
import atexit
import fcntl
from .logger import setup_logger
logger = setup_logger(__name__)

# CSS styling for the tray popup menu (solid dark background for readability)
_MENU_CSS = b"""
menu {
    background-color: #2d2d2d;
    border: 1px solid #1a1a1a;
    border-radius: 8px;
    padding: 4px 0;
}
menuitem {
    padding: 6px 12px;
    color: #ffffff;
}
menuitem:hover {
    background-color: #404040;
}
menuitem:disabled {
    color: #888888;
}
menuitem label {
    color: inherit;
}
separator {
    background-color: #404040;
    margin: 4px 8px;
}
"""

# D-Bus service import (optional - only needed for GNOME extension)
try:
    from .dbus_service import TalkTypeDBusService
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False
    logger.warning("D-Bus service not available - GNOME extension integration disabled")

def _runtime_dir():
    return os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")


def _acquire_tray_singleton():
    """
    Acquire singleton lock using fcntl to prevent race conditions.
    Uses file locking which is atomic and prevents multiple instances.
    The lock is held for the lifetime of the process and auto-released on exit.
    """
    lockfile_path = os.path.join(_runtime_dir(), "talktype-tray.lock")
    try:
        # Open lock file (create if doesn't exist)
        lockfile = open(lockfile_path, "w")

        # Try to acquire exclusive lock (non-blocking)
        # LOCK_EX = exclusive lock, LOCK_NB = non-blocking
        fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        # If we got here, we acquired the lock successfully
        # Write our PID for informational purposes
        lockfile.write(str(os.getpid()))
        lockfile.flush()

        # Keep the file open for the process lifetime
        # The lock will automatically be released when the process exits
        # Store in global to prevent garbage collection
        global _tray_lockfile_handle
        _tray_lockfile_handle = lockfile

        logger.debug(f"Acquired tray singleton lock: {lockfile_path}")

    except IOError:
        # Lock is already held by another process
        print("Another tray instance is already running. Exiting.", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Warning: could not acquire tray singleton lock: {e}", file=sys.stderr)

# Global to keep lock file open
_tray_lockfile_handle = None

class DictationTray:
    def __init__(self):
        # TalkType is a dark-themed app: Preferences and the onboarding windows
        # each set gtk-application-prefer-dark-theme individually. The dialogs the
        # TRAY spawns (About, "Check for Updates" result) did not, so they rendered
        # in the light system GTK theme on a dark desktop. This is a global Gtk
        # setting, so setting it once here — before any tray dialog is built —
        # makes every tray window match the rest of the app.
        try:
            _settings = Gtk.Settings.get_default()
            if _settings is not None:
                _settings.set_property("gtk-application-prefer-dark-theme", True)
        except Exception as e:
            logger.debug(f"Could not set dark theme preference: {e}")

        self.indicator = AppIndicator3.Indicator.new(
            "talktype",
            "microphone-sensitivity-muted",  # start with muted icon
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )

        # Check if we should show the GTK tray
        # In production: hide GTK tray if GNOME extension is enabled
        # In dev mode (DEV_MODE=1): always show GTK tray for testing
        self._should_show_tray = self._check_tray_visibility()

        if self._should_show_tray:
            self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            logger.info("GTK tray enabled")
        else:
            self.indicator.set_status(AppIndicator3.IndicatorStatus.PASSIVE)
            logger.info("GTK tray hidden (GNOME extension is active)")

        self.indicator.set_title("TalkType")  # Set the app name

        # Track subprocess windows
        self.preferences_process = None

        # Cached PID of the dictation service (for fast /proc-based status checks)
        self._service_pid = None

        # Track onboarding state - service should not start during onboarding
        self.onboarding_in_progress = False

        # Initialize D-Bus service (optional - for GNOME extension integration)
        self.dbus_service = None
        self._init_dbus_service()

        self.update_icon_status()
        self.indicator.set_menu(self.build_menu())

        # Track service state for change detection
        self._last_service_state = self.is_service_running()

        # Check service status every 1 second and update menu (faster sync in dev mode)
        GLib.timeout_add_seconds(1, self.update_status_and_menu)

        # Auto-start will be triggered after welcome dialog on first run
        # or immediately if not first run (handled in main())

    def _check_tray_visibility(self) -> bool:
        """
        Determine if GTK tray should be visible.

        Returns:
            bool: True if GTK tray should be shown, False if it should be hidden
        """
        # Check for dev mode first - always show in dev mode
        if os.environ.get('DEV_MODE') == '1':
            logger.info("DEV_MODE=1 detected - showing GTK tray for testing")
            return True

        # Check if GNOME extension is enabled
        try:
            from . import extension_helper
            if extension_helper.is_extension_enabled():
                logger.info("GNOME extension is enabled - hiding GTK tray")
                return False
        except Exception as e:
            logger.debug(f"Could not check extension status: {e}")

        # Default: show GTK tray (extension not enabled or not GNOME)
        return True

    def _init_dbus_service(self):
        """Initialize D-Bus service for GNOME extension integration (optional)."""
        if not DBUS_AVAILABLE:
            return

        try:
            # Create a minimal app instance for D-Bus
            class TrayAppInstance:
                """Minimal app instance for D-Bus integration with tray."""
                def __init__(self, tray):
                    self.tray = tray
                    self.is_recording = False

                @property
                def service_running(self):
                    """Get current service running state."""
                    return self.tray.is_service_running()

                def start_service(self):
                    """Start service via tray."""
                    GLib.idle_add(self.tray.start_service, None)

                def stop_service(self):
                    """Stop service via tray."""
                    GLib.idle_add(self.tray.stop_service, None)

                def restart_service(self):
                    """Restart service via tray."""
                    GLib.idle_add(self.tray.restart_service, None)

                def toggle_recording(self):
                    """Toggle recording in the service process via SIGUSR1."""
                    pid = getattr(self.tray, '_service_pid', None)
                    if pid:
                        try:
                            os.kill(pid, signal.SIGUSR1)
                        except (ProcessLookupError, PermissionError):
                            pass

                def start_recording(self):
                    """Start recording if not already recording."""
                    if not self.is_recording:
                        self.toggle_recording()

                def stop_recording(self):
                    """Stop recording if currently recording."""
                    if self.is_recording:
                        self.toggle_recording()

                def show_preferences(self):
                    """Open preferences via tray."""
                    GLib.idle_add(self.tray.open_preferences, None)

                def show_update_result(self, result):
                    """Show the persistent update-result dialog via the tray (called from
                    the GNOME extension's D-Bus CheckForUpdates so the manual check gives a
                    real 'click OK' window, not just the fleeting GNOME notification)."""
                    GLib.idle_add(self.tray._show_update_result_dialog, result)

                def show_help(self):
                    """Show help via tray."""
                    GLib.idle_add(self.tray.show_help, None)

                def show_voice_commands(self):
                    """Show voice commands quick reference via tray."""
                    GLib.idle_add(self.tray.show_voice_commands, None)

                def show_about(self):
                    """Show about dialog via tray."""
                    GLib.idle_add(self.tray.show_about_dialog, None)

                def show_preferences_updates(self):
                    """Open preferences to Updates tab via tray."""
                    GLib.idle_add(self.tray.open_preferences_updates, None)

                def set_performance_preset(self, preset_id: str):
                    """Apply a performance preset via tray (called from GNOME extension D-Bus)."""
                    GLib.idle_add(self.tray.set_performance_preset, preset_id)

                def set_injection_mode(self, mode: str):
                    """Set text injection mode via tray (called from GNOME extension D-Bus)."""
                    GLib.idle_add(self.tray.set_injection_mode, mode)

                def set_model(self, model_name: str):
                    """Change the model via tray (called from GNOME extension D-Bus).

                    Without this method, DBusService._dispatch's hasattr check
                    failed and SetModel was silently discarded.
                    """
                    GLib.idle_add(self.tray.set_model, model_name)

                def quit(self):
                    """Quit via tray."""
                    GLib.idle_add(self.tray.quit_app, None)

                @property
                def config(self):
                    """Get current config."""
                    try:
                        from .config import load_config
                        return load_config()
                    except Exception:
                        # Return minimal config
                        class MinimalConfig:
                            model = 'large-v3'
                            device = 'cpu'
                        return MinimalConfig()

            app_instance = TrayAppInstance(self)
            self.dbus_service = TalkTypeDBusService(app_instance)
            logger.info("D-Bus service initialized for GNOME extension integration")
        except Exception as e:
            logger.warning(f"Failed to initialize D-Bus service: {e}")
            self.dbus_service = None

    def is_service_running(self):
        """Check if the dictation service is active via /proc (no subprocess spawn).

        Uses a cached PID for fast lookups. Falls back to scanning /proc if
        the PID is unknown (e.g., service was started before the tray).
        """
        # Fast path: check cached PID directly via /proc
        pid = getattr(self, '_service_pid', None)
        if pid:
            if self._check_pid_is_service(pid):
                return True
            # PID no longer valid — clear it
            self._service_pid = None

        # Slow path: scan /proc to find an existing service process
        # (handles case where service started before tray, e.g., at boot)
        try:
            my_pid = os.getpid()
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
                entry_pid = int(entry)
                if entry_pid == my_pid:
                    continue
                if self._check_pid_is_service(entry_pid):
                    self._service_pid = entry_pid
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def _check_pid_is_service(pid):
        """Check if a given PID is a TalkType dictation service process."""
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().decode(errors="ignore")
            return "talktype.app" in cmd or "bin/dictate" in cmd
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            return False

    def _auto_start_service(self):
        """Auto-start the dictation service if not already running."""
        try:
            # NEVER start during onboarding - hotkey test needs to capture keys
            if self.onboarding_in_progress:
                logger.info("Onboarding in progress - refusing to auto-start service")
                return False

            # Only start if not already running
            if not self.is_service_running():
                logger.info("Auto-starting dictation service...")
                self.start_service(None)
            else:
                logger.info("Dictation service already running, skipping auto-start")
        except Exception as e:
            logger.error(f"Failed to auto-start service: {e}", exc_info=True)
        return False  # Don't repeat this timer

    def update_icon_status(self, is_running=None):
        """Update icon based on service status.

        Args:
            is_running: Pre-computed service state (avoids redundant checks).
                        If None, checks service status directly.
        """
        if is_running is None:
            is_running = self.is_service_running()
        if is_running:
            self.indicator.set_icon_full("microphone-sensitivity-high", "TalkType: Active")
        else:
            self.indicator.set_icon_full("microphone-sensitivity-muted", "TalkType: Stopped")
        return True  # Continue the timer

    def _emit_service_state_after_check(self, expected_state):
        """Emit D-Bus service state signal after verifying actual state."""
        if not self.dbus_service:
            return False

        # Check actual service state
        actual_state = self.is_service_running()

        # Emit the actual state (not expected, in case it didn't start/stop)
        try:
            self.dbus_service.emit_service_state(actual_state)
            logger.debug(f"Emitted D-Bus service state: {actual_state}")
        except Exception as e:
            logger.error(f"Failed to emit D-Bus service state: {e}")

        return False  # Don't repeat
    
    # ----- Service management helpers -----

    def _get_dev_pythonpath(self):
        """Build PYTHONPATH for dev mode (includes src/ and system PyGObject).

        Returns the PYTHONPATH string if in dev mode, or None for AppImage.
        """
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        src_dir_check = os.path.join(project_root, "src")
        if os.path.exists(src_dir_check):
            return ":".join([
                os.path.abspath(src_dir_check),
                "/usr/lib64/python3.14/site-packages",
                "/usr/lib/python3.14/site-packages",
            ])
        return None

    def _launch_service(self):
        """Launch the dictation service subprocess.

        Finds the dictate script (AppImage) or falls back to python -m (dev mode).
        """
        # AppImage path: __file__ → usr/src/talktype/tray.py → usr/bin/dictate
        # Delegated so the tray and Preferences start the service identically.
        # They used to spawn it separately and only this copy set GDK_BACKEND,
        # so a restart from Preferences ran the service on native Wayland and
        # the recording indicator ignored indicator_position. See
        # service_launcher for why the backend matters.
        from .service_launcher import launch_dictation_service

        proc = launch_dictation_service()
        if proc is not None:
            self._service_pid = proc.pid

    def _kill_service(self):
        """Kill all running dictation service processes."""
        subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
        subprocess.run(["pkill", "-f", "bin/dictate"], capture_output=True)

    def start_service(self, _):
        """Start the dictation service directly."""
        # CRITICAL: Never start service during onboarding - hotkeys must not be active
        if self.onboarding_in_progress:
            logger.info("Onboarding in progress - refusing to start service")
            return

        try:
            self._launch_service()

            # Emit D-Bus signal if available
            if self.dbus_service:
                GLib.timeout_add_seconds(1, lambda: self._emit_service_state_after_check(True))
        except Exception as e:
            logger.error(f"Failed to start service: {e}", exc_info=True)
        GLib.timeout_add_seconds(1, lambda: self.update_status_and_menu(repeat=False))

    def stop_service(self, _):
        """Stop the dictation service directly."""
        try:
            self._kill_service()
            logger.info("Stopped dictation service")

            # Emit D-Bus signal if available
            if self.dbus_service:
                GLib.timeout_add_seconds(1, lambda: self._emit_service_state_after_check(False))
        except Exception as e:
            logger.error(f"Failed to stop service: {e}")
        GLib.timeout_add_seconds(1, lambda: self.update_status_and_menu(repeat=False))

    def restart_service(self, _):
        """Restart the dictation service directly.

        The kill/wait/relaunch runs on a background thread so the 1-second
        wait for processes to die never freezes the tray/menu (this fires on
        every injection-mode and performance-preset change).
        """
        # CRITICAL: Never restart service during onboarding
        if self.onboarding_in_progress:
            logger.info("Onboarding in progress - refusing to restart service")
            return

        # Re-entrancy guard: the old synchronous version was serialized by the
        # blocking sleep on the main loop. Now that the work runs on a thread,
        # a second restart (injection-mode + preset changes both trigger one)
        # firing within the 1s window could kill the freshly-launched service
        # or leave two backends both grabbing the hotkey (double-typing).
        if getattr(self, '_restarting', False):
            logger.info("Restart already in progress - ignoring duplicate request")
            return
        self._restarting = True

        import threading

        def _do_restart():
            try:
                self._kill_service()
                time.sleep(1)  # Wait for processes to terminate
                GLib.idle_add(self._launch_service)
            except Exception as e:
                logger.error(f"Failed to restart service: {e}", exc_info=True)

            def _finish():
                self.update_status_and_menu(repeat=False)
                self._restarting = False
                return False
            GLib.timeout_add_seconds(2, _finish)

        threading.Thread(target=_do_restart, daemon=True).start()
    
    def update_status_and_menu(self, repeat=True):
        """Update icon and menu display based on service status.

        Args:
            repeat: If True (default), keeps the GLib timer running.
                    Pass False for a one-shot update.
        """
        # Store previous state to detect changes
        old_state = getattr(self, '_last_service_state', None)
        new_state = self.is_service_running()

        # Update UI — pass pre-computed state to avoid redundant checks
        self.update_icon_status(is_running=new_state)
        self.update_menu_display(is_running=new_state)

        # If state changed, emit D-Bus signal
        if old_state is not None and old_state != new_state:
            logger.info(f"Service state changed: {old_state} -> {new_state}")
            if self.dbus_service:
                try:
                    self.dbus_service.emit_service_state(new_state)
                    logger.debug(f"Emitted D-Bus service state: {new_state}")
                except Exception as e:
                    logger.error(f"Failed to emit D-Bus service state: {e}")

        self._last_service_state = new_state
        return repeat

    def toggle_service(self, widget):
        """Toggle dictation service on/off."""
        # Prevent recursive calls when we programmatically set the toggle
        if hasattr(self, '_updating_toggle') and self._updating_toggle:
            return

        if widget.get_active():
            # Turn service ON
            self.start_service(None)
        else:
            # Turn service OFF
            self.stop_service(None)

    def _emit_model_changed(self, model_name: str):
        """Tell the GNOME extension that a model/device change has committed.

        This process owns the D-Bus name the extension listens on, so the signal
        has to originate here. Best-effort: the config is already saved by the
        time this runs, so a bus problem must not fail the change itself.
        """
        if not self.dbus_service:
            return
        try:
            self.dbus_service.emit_model_changed(model_name)
            logger.info(f"Announced model change to extension: {model_name}")
        except Exception as e:
            logger.error(f"Failed to emit model change: {e}")

    def set_model(self, model_name: str):
        """Change the Whisper model. Reachable over D-Bus as SetModel.

        The D-Bus interface has always advertised SetModel, but nothing
        implemented it here — and DBusService._dispatch silently drops calls
        for methods the app object does not have, so it failed without a
        word. (The one implementation that did exist wrote to a JSON path
        this app has never read.) Follows the same sequence as applying a
        performance preset: persist, tell the extension, restart.
        """
        from .config import VALID_MODELS, load_config, save_config

        if model_name not in VALID_MODELS:
            logger.error(
                f"SetModel: refusing unknown model {model_name!r}. "
                f"Valid: {', '.join(sorted(VALID_MODELS))}"
            )
            return

        try:
            cfg = load_config()
            if cfg.model == model_name:
                logger.info(f"SetModel: already using {model_name}")
                return
            cfg.model = model_name
            save_config(cfg)
            logger.info(f"SetModel: switched to {model_name}")

            self.update_menu_display()
            # The tray owns the D-Bus name the extension listens on, so the
            # change notification has to be emitted from here.
            self._emit_model_changed(model_name)
            self.restart_service(None)
        except Exception as e:
            logger.error(f"SetModel failed: {e}", exc_info=True)

    def set_injection_mode(self, mode: str):
        """Set the injection mode (auto, type, or paste)."""
        # Prevent recursive calls when we programmatically set the radio buttons
        if hasattr(self, '_updating_injection_mode') and self._updating_injection_mode:
            return

        try:
            from .config import load_config, save_config
            cfg = load_config()
            cfg.injection_mode = mode

            # Save the config
            save_config(cfg)

            # Notify user
            from .app import _notify
            mode_names = {
                "auto": "Auto (Smart Detection)",
                "type": "Keyboard Typing",
                "paste": "Clipboard Paste"
            }
            mode_name = mode_names.get(mode, mode)
            logger.info(f"Switched to {mode_name} mode")
            _notify("TalkType", f"Input mode: {mode_name}")

            # Notify GNOME extension of mode change via D-Bus signal
            if self.dbus_service:
                try:
                    self.dbus_service.emit_injection_mode_changed(mode)
                except Exception as e:
                    logger.error(f"Failed to emit injection mode change: {e}")

            # Restart service so new injection mode takes effect immediately
            self.restart_service(None)

        except Exception as e:
            logger.error(f"Failed to set injection mode: {e}")

    # Performance preset definitions
    # Each preset defines: model, device
    PERFORMANCE_PRESETS = {
        "fastest": {
            "label": "Fastest",
            "description": "tiny model, CPU",
            "model": "tiny",
            "device": "cpu"
        },
        "light": {
            "label": "Light",
            "description": "base model, CPU",
            "model": "base",
            "device": "cpu"
        },
        "balanced": {
            "label": "Balanced",
            "description": "small model, GPU if available",
            "model": "small",
            "device": "cuda"  # Will fall back to CPU if no GPU
        },
        "quality": {
            "label": "Quality",
            "description": "medium model, GPU if available",
            "model": "medium",
            "device": "cuda"  # Will fall back to CPU if no GPU
        },
        "accurate": {
            "label": "Most Accurate",
            "description": "large-v3 model, GPU",
            "model": "large-v3",
            "device": "cuda"
        },
        "battery": {
            "label": "Battery Saver",
            "description": "tiny model, CPU, short timeout",
            "model": "tiny",
            "device": "cpu",
            # The short timeout is what distinguishes this from "Fastest" —
            # they are otherwise the same tiny/CPU pair. Declaring it here
            # rather than hard-coding it in set_performance_preset() lets
            # _get_current_preset() tell the two apart, which it previously
            # could not: it matched on model+device and returned the first
            # hit, so Battery Saver could never show as the active preset.
            "auto_timeout_enabled": True,
            "auto_timeout_minutes": 2,
        }
    }

    # Preset keys that are settings to compare/apply, beyond model and device.
    _PRESET_EXTRA_KEYS = ("auto_timeout_enabled", "auto_timeout_minutes")

    def _get_current_preset(self) -> str:
        """
        Determine which preset matches current settings, or 'custom' if none match.
        Match primarily by model - device varies by available hardware.
        """
        try:
            from .config import load_config
            cfg = load_config()

            def extras_match(preset):
                """Presets that declare extra settings must match those too.

                Without this, two presets sharing a model/device pair are
                indistinguishable and the earlier one always wins.
                """
                return all(
                    getattr(cfg, key, None) == preset[key]
                    for key in self._PRESET_EXTRA_KEYS
                    if key in preset
                )

            def declares_extras(preset):
                return any(k in preset for k in self._PRESET_EXTRA_KEYS)

            # Most specific first: only presets that declare extra settings,
            # and only when those match too. Checking the less specific
            # presets first would let "Fastest" claim a "Battery Saver"
            # config, since the two share their model and device.
            for preset_id, preset in self.PERFORMANCE_PRESETS.items():
                if (declares_extras(preset)
                        and cfg.model == preset["model"]
                        and cfg.device == preset["device"]
                        and extras_match(preset)):
                    return preset_id

            # Then model + device, for presets that declare no extras.
            for preset_id, preset in self.PERFORMANCE_PRESETS.items():
                if (cfg.model == preset["model"] and cfg.device == preset["device"]
                        and not any(k in preset for k in self._PRESET_EXTRA_KEYS)):
                    return preset_id

            # Fall back to model-only match (device may differ due to hardware)
            for preset_id, preset in self.PERFORMANCE_PRESETS.items():
                if (cfg.model == preset["model"]
                        and not any(k in preset for k in self._PRESET_EXTRA_KEYS)):
                    return preset_id

            return "custom"
        except Exception:
            return "custom"

    def set_performance_preset(self, preset_id: str):
        """Apply a performance preset."""
        # Prevent recursive calls when programmatically setting radio buttons
        if hasattr(self, '_updating_preset') and self._updating_preset:
            return

        if preset_id == "custom" or preset_id not in self.PERFORMANCE_PRESETS:
            return

        preset = self.PERFORMANCE_PRESETS[preset_id]
        model_name = preset["model"]

        try:
            from .config import load_config, save_config
            from .model_helper import is_model_cached_fast, download_model_with_progress

            # large-v3 requires NVIDIA GPU + CUDA libraries.
            # Check BEFORE anything else — if CUDA missing, show a dialog and bail out.
            # NOTE: This block is intentionally outside the inner try/except so that
            # an exception here CANNOT fall through to the model download below.
            if model_name == "large-v3":
                _cuda_ok = False
                try:
                    from .cuda_helper import has_talktype_cuda_libraries
                    _cuda_ok = has_talktype_cuda_libraries()
                except Exception as _e:
                    logger.error(f"CUDA check error: {_e}")
                    _cuda_ok = False  # Treat as missing — safer than allowing large-v3

                if not _cuda_ok:
                    # Detect NVIDIA GPU for the right error message and action
                    _has_nvidia = False
                    try:
                        from .cuda_helper import detect_nvidia_gpu
                        _has_nvidia = bool(detect_nvidia_gpu())
                    except Exception:
                        pass

                    # Revert the radio button back to current preset (do this before
                    # showing any dialog so the UI is already correct if user cancels)
                    self._updating_preset = True
                    try:
                        _cur = self._get_current_preset()
                        if _cur in self.preset_radios:
                            self.preset_radios[_cur].set_active(True)
                        elif hasattr(self, 'preset_custom'):
                            self.preset_custom.set_active(True)
                    except Exception as _re:
                        logger.error(f"Failed to revert preset radio: {_re}")
                    finally:
                        self._updating_preset = False

                    if _has_nvidia:
                        # NVIDIA GPU detected — offer to download BOTH CUDA + large-v3 together.
                        # One confirmation, then one unified dialog showing both progress bars.
                        _dlg = Gtk.MessageDialog(
                            parent=None,
                            flags=0,
                            message_type=Gtk.MessageType.QUESTION,
                            buttons=Gtk.ButtonsType.YES_NO,
                            text="Download Required for 'Most Accurate'"
                        )
                        _dlg.format_secondary_text(
                            "Two components need to be downloaded before 'Most Accurate' can be used:\n\n"
                            "  • CUDA GPU Libraries   (~1.4GB)\n"
                            "  • Large-v3 AI Model    (~3GB)\n\n"
                            "Total: ~4.4GB — one-time download, cached for future use.\n\n"
                            "Would you like to download both now?"
                        )
                        _dlg.set_keep_above(True)
                        _response = _dlg.run()
                        _dlg.destroy()
                        if _response == Gtk.ResponseType.YES:
                            # Show the unified dialog — this blocks until both downloads finish
                            # (or are cancelled).  After both succeed, auto-apply the preset.
                            from .download_progress_dialog import show_unified_download_dialog
                            _results = show_unified_download_dialog(
                                cuda=True,
                                model="large-v3",
                            )
                            _cuda_ok = _results.get("CUDA Libraries", {}).get("success", False)
                            _model_ok = _results.get("large-v3 AI Model", {}).get("success", False)
                            if _cuda_ok and _model_ok:
                                # Both downloads succeeded — save the preset config and
                                # restart the dictation service so it picks up CUDA + large-v3.
                                try:
                                    cfg = load_config()
                                    cfg.model = "large-v3"
                                    cfg.device = "cuda"
                                    save_config(cfg)
                                    logger.info(
                                        "Both downloads complete — applied Most Accurate preset "
                                        "(large-v3, cuda)"
                                    )
                                    self.update_menu_display()
                                    self.restart_service(None)
                                except Exception as _ae:
                                    logger.error(f"Failed to apply preset after download: {_ae}")
                    else:
                        # No NVIDIA GPU — just inform, no download to offer
                        _dlg = Gtk.MessageDialog(
                            parent=None,
                            flags=0,
                            message_type=Gtk.MessageType.WARNING,
                            buttons=Gtk.ButtonsType.OK,
                            text="Cannot Apply 'Most Accurate' Preset"
                        )
                        _dlg.format_secondary_text(
                            "'Most Accurate' requires an NVIDIA GPU + CUDA libraries.\n\n"
                            "AMD and Intel GPUs are not supported for the large-v3 model.\n"
                            "Please choose a different performance preset."
                        )
                        _dlg.set_keep_above(True)
                        _dlg.run()
                        _dlg.destroy()

                    return  # Always stop here — never fall through to model download

            # Check if model is cached. The fast variant answers this from
            # file presence; is_model_cached() answered it by constructing a
            # real WhisperModel, which blocks this GTK main loop for seconds
            # to tens of seconds on large-v3. While it is blocked the tray
            # dispatches no D-Bus, and the dictation service calls into the
            # tray from the thread that holds an exclusive grab on every
            # keyboard — so this call could freeze the whole system's input.
            if not is_model_cached_fast(model_name):
                logger.info(f"Model {model_name} not cached, showing download dialog")
                # Show download dialog - this returns the model or None if cancelled
                model = download_model_with_progress(model_name, device="cpu", show_confirmation=True)
                if model is None:
                    # User cancelled download or download failed
                    logger.info(f"Model download cancelled for preset {preset_id}")
                    # Revert radio button to current preset
                    self._updating_preset = True
                    current_preset = self._get_current_preset()
                    if current_preset in self.preset_radios:
                        self.preset_radios[current_preset].set_active(True)
                    elif hasattr(self, 'preset_custom'):
                        self.preset_custom.set_active(True)
                    self._updating_preset = False
                    return
                else:
                    # Model downloaded successfully, free it (will be loaded by service)
                    del model
                    logger.info(f"Model {model_name} downloaded successfully")

            cfg = load_config()

            # Determine effective device — presets marked "cuda" require CUDA libraries.
            # If CUDA isn't installed, silently use CPU so the service doesn't crash.
            effective_device = preset["device"]
            if effective_device == "cuda":
                try:
                    from .cuda_helper import has_talktype_cuda_libraries
                    if not has_talktype_cuda_libraries():
                        effective_device = "cpu"
                        logger.info(
                            f"Preset '{preset_id}' requests CUDA but libraries not installed — "
                            "saving device=cpu to prevent service crash."
                        )
                except Exception:
                    effective_device = "cpu"  # Safer to assume no CUDA if check fails

            # Apply preset settings
            cfg.model = preset["model"]
            cfg.device = effective_device

            # Battery saver also reduces timeout
            # Apply any extra settings the preset declares, so what gets saved
            # is exactly what _get_current_preset() matches against.
            for key in self._PRESET_EXTRA_KEYS:
                if key in preset:
                    setattr(cfg, key, preset[key])

            # Save config
            save_config(cfg)

            # Notify user
            from .app import _notify
            logger.info(f"Applied performance preset: {preset['label']}")
            _notify("TalkType", f"Performance: {preset['label']}\nRestarting service...")

            # Update menu display
            self.update_menu_display()

            # Tell the GNOME extension the change actually took effect. The
            # tray owns the D-Bus name the extension listens on, so this has to
            # be emitted here — emitting it from the dictation service (which
            # does not own the name) never reaches the extension, which is why
            # its menu kept showing the previous model indefinitely.
            self._emit_model_changed(cfg.model)

            # Restart service to apply new model
            self.restart_service(None)

        except Exception as e:
            logger.error(f"Failed to apply performance preset: {e}")

    def update_menu_display(self, is_running=None):
        """Update menu display with current service status and model.

        Args:
            is_running: Pre-computed service state (avoids redundant checks).
                        If None, checks service status directly.
        """
        if hasattr(self, 'service_toggle'):
            # Update service toggle state
            if is_running is None:
                is_running = self.is_service_running()
            self._updating_toggle = True
            self.service_toggle.set_active(is_running)
            self._updating_toggle = False

        # Update active model display
        if hasattr(self, 'model_display_item'):
            try:
                from .config import load_config
                cfg = load_config()
                model_names = {
                    'tiny': 'Tiny (fastest)',
                    'base': 'Base',
                    'small': 'Small',
                    'medium': 'Medium',
                    'large-v3': 'Large (best quality)',
                    'large': 'Large (best quality)'
                }
                display_name = model_names.get(cfg.model, cfg.model)
                self.model_display_item.set_label(f"Active Model: {display_name}")

                # Update device display
                device_names = {
                    'cpu': 'CPU',
                    'cuda': 'GPU (CUDA)'
                }
                device_display = device_names.get(cfg.device, cfg.device.upper())
                self.device_display_item.set_label(f"Device: {device_display}")

                # Update injection mode radio buttons
                if hasattr(self, 'injection_mode_auto'):
                    self._updating_injection_mode = True
                    mode = cfg.injection_mode.lower()
                    if mode == "auto":
                        self.injection_mode_auto.set_active(True)
                    elif mode == "paste":
                        self.injection_mode_paste.set_active(True)
                    else:  # default to "type"
                        self.injection_mode_type.set_active(True)
                    self._updating_injection_mode = False

                # Update performance preset radio buttons
                if hasattr(self, 'preset_radios'):
                    self._updating_preset = True
                    current_preset = self._get_current_preset()
                    if current_preset in self.preset_radios:
                        self.preset_radios[current_preset].set_active(True)
                    elif hasattr(self, 'preset_custom'):
                        self.preset_custom.set_active(True)
                    self._updating_preset = False
            except Exception as e:
                logger.error(f"Failed to update model/device display: {e}")
                self.model_display_item.set_label("Active Model: Unknown")
                self.device_display_item.set_label("Device: Unknown")
    
    def _launch_preferences(self, tab=None):
        """Launch the preferences window subprocess.

        Args:
            tab: Optional tab name to open directly (e.g. "updates").
        """
        # Don't open a second window
        if self.preferences_process and self.preferences_process.poll() is None:
            logger.info("Preferences window already open")
            return

        tab_desc = f" ({tab} tab)" if tab else ""

        # AppImage path: __file__ → usr/src/talktype/tray.py → usr/bin/dictate-prefs
        src_dir = os.path.dirname(__file__)
        usr_dir = os.path.dirname(os.path.dirname(src_dir))
        prefs_script = os.path.join(usr_dir, "bin", "dictate-prefs")

        if os.path.exists(prefs_script):
            cmd = [prefs_script]
            if tab:
                cmd.append(f"--tab={tab}")
            self.preferences_process = subprocess.Popen(cmd, env=os.environ.copy())
            logger.info(f"Opened preferences{tab_desc} via {prefs_script}")
        else:
            # Dev mode fallback
            env = os.environ.copy()
            pythonpath = self._get_dev_pythonpath()
            if pythonpath:
                # Prefs also needs Python 3.13 paths for GTK bindings
                pythonpath += ":/usr/lib64/python3.13/site-packages:/usr/lib/python3.13/site-packages"
                env["PYTHONPATH"] = pythonpath
            cmd = [sys.executable, "-m", "talktype.prefs"]
            if tab:
                cmd.append(f"--tab={tab}")
            self.preferences_process = subprocess.Popen(cmd, env=env)
            logger.info(f"Opened preferences{tab_desc} via Python module")

    def open_preferences(self, _):
        """Launch preferences window."""
        try:
            self._launch_preferences()
        except Exception as e:
            logger.error(f"Failed to open preferences: {e}")

    def open_preferences_updates(self, _):
        """Launch preferences window directly to Updates tab."""
        try:
            self._launch_preferences(tab="updates")
        except Exception as e:
            logger.error(f"Failed to open preferences updates tab: {e}")

    def download_cuda(self, _):
        """Download CUDA libraries for GPU acceleration."""
        # Show confirmation dialog first
        confirm_dialog = Gtk.MessageDialog(
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Download CUDA Libraries?"
        )
        from talktype.config import get_data_dir
        cuda_path = os.path.join(get_data_dir(), "cuda")
        confirm_dialog.format_secondary_text(
            "This will download approximately 1.4GB of CUDA libraries for GPU acceleration.\n\n"
            f"The files will be stored in {cuda_path} and may take several minutes to download.\n\n"
            "Continue with download?"
        )
        confirm_dialog.set_position(Gtk.WindowPosition.CENTER)
        confirm_dialog.set_keep_above(True)
        response = confirm_dialog.run()
        confirm_dialog.destroy()

        if response != Gtk.ResponseType.YES:
            logger.info("CUDA download cancelled by user")
            return

        try:
            from . import cuda_helper
            logger.info("Starting CUDA download...")
            success = cuda_helper.download_cuda_libraries()
            if success:
                logger.info("CUDA libraries downloaded successfully")
                # Auto-switch to CUDA in config after successful download
                try:
                    from .config import load_config, save_config
                    cfg = load_config()
                    if cfg.device != "cuda":
                        cfg.device = "cuda"
                        save_config(cfg)
                        logger.info("✅ Automatically switched to GPU mode after CUDA download")
                        # Refresh menu to show updated device
                        self.update_menu_display()
                        # The device changed under the extension's feet — tell it,
                        # or its Device line and preset dot stay on the old value.
                        self._emit_model_changed(cfg.model)
                except Exception as save_e:
                    logger.warning(f"Could not auto-enable GPU mode: {save_e}")
            else:
                logger.error("CUDA download failed")
        except Exception as e:
            logger.error(f"Error downloading CUDA: {e}")
    
    def show_help(self, _):
        """Show help dialog with TalkType features and instructions."""
        from .help_dialog import show_help_dialog
        show_help_dialog()

    def show_voice_commands(self, _):
        """Show voice commands quick reference popup."""
        from .voice_commands_dialog import show_voice_commands_dialog
        show_voice_commands_dialog()

    def show_about_dialog(self, _):
        """Show About dialog with app info, version, and changelog."""
        import threading
        from . import __version__
        from . import update_checker

        # Create custom dialog for more flexibility
        dialog = Gtk.Dialog(
            title="About TalkType",
            flags=Gtk.DialogFlags.MODAL
        )
        dialog.set_default_size(500, 450)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        dialog.set_keep_above(True)

        content = dialog.get_content_area()
        content.set_spacing(10)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(10)

        # App icon
        try:
            icon_paths = [
                "/usr/share/icons/hicolor/128x128/apps/talktype.png",
                os.path.join(os.path.dirname(__file__), "icons", "talktype-128.png"),
            ]
            for icon_path in icon_paths:
                if os.path.exists(icon_path):
                    from gi.repository import GdkPixbuf
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path, 64, 64, True)
                    icon = Gtk.Image.new_from_pixbuf(pixbuf)
                    content.pack_start(icon, False, False, 0)
                    break
        except Exception as e:
            logger.debug(f"Could not load icon for About dialog: {e}")

        # App name and version
        title_label = Gtk.Label()
        title_label.set_markup(f'<span size="x-large"><b>TalkType</b></span>')
        content.pack_start(title_label, False, False, 0)

        version_label = Gtk.Label(label=f"Version {__version__}")
        content.pack_start(version_label, False, False, 0)

        desc_label = Gtk.Label(label="AI-powered speech recognition and dictation for Linux")
        desc_label.set_line_wrap(True)
        content.pack_start(desc_label, False, False, 5)

        # Copyright and author
        copyright_label = Gtk.Label()
        copyright_label.set_markup('<span size="small">© 2024-2025 Ron B. • MIT License</span>')
        content.pack_start(copyright_label, False, False, 0)

        # What's New section
        whats_new_label = Gtk.Label()
        whats_new_label.set_markup('<b>What\'s New in This Version</b>')
        whats_new_label.set_xalign(0)
        whats_new_label.set_margin_top(15)
        content.pack_start(whats_new_label, False, False, 0)

        # Scrolled text view for release notes
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(150)

        self._about_notes_text = Gtk.TextView()
        self._about_notes_text.set_editable(False)
        self._about_notes_text.set_wrap_mode(Gtk.WrapMode.WORD)
        self._about_notes_text.set_left_margin(10)
        self._about_notes_text.set_right_margin(10)
        self._about_notes_text.set_top_margin(10)
        self._about_notes_text.get_buffer().set_text("Loading release notes...")
        scroll.add(self._about_notes_text)
        content.pack_start(scroll, True, True, 0)

        # Links box
        links_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        links_box.set_halign(Gtk.Align.CENTER)
        links_box.set_margin_top(10)

        # GitHub link
        github_btn = Gtk.LinkButton.new_with_label(
            "https://github.com/ronb1964/TalkType",
            "GitHub Repository"
        )
        links_box.pack_start(github_btn, False, False, 0)

        # Full changelog link
        changelog_btn = Gtk.LinkButton.new_with_label(
            update_checker.get_releases_url(),
            "View Full Changelog"
        )
        links_box.pack_start(changelog_btn, False, False, 0)

        content.pack_start(links_box, False, False, 0)

        # Close button
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)

        dialog.show_all()

        # Fetch release notes in background
        def fetch_notes():
            release = update_checker.fetch_release_by_tag(__version__)
            if release and release.get("body"):
                notes = release["body"]
            else:
                notes = "Release notes not available.\n\nVisit GitHub for the full changelog."
            GLib.idle_add(lambda: self._about_notes_text.get_buffer().set_text(notes))

        thread = threading.Thread(target=fetch_notes, daemon=True)
        thread.start()

        dialog.run()
        dialog.destroy()

    def check_for_updates_clicked(self, _):
        """Check for updates and show results dialog."""
        import threading
        from . import update_checker

        # Create progress dialog
        progress_dialog = Gtk.MessageDialog(
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.NONE,
            text="Checking for Updates..."
        )
        progress_dialog.format_secondary_text("Connecting to GitHub...")
        progress_dialog.set_position(Gtk.WindowPosition.CENTER)
        progress_dialog.set_keep_above(True)
        progress_dialog.show_all()

        result_holder = [None]

        def do_check():
            """Background thread to check for updates."""
            try:
                result_holder[0] = update_checker.check_for_updates()
            except Exception as e:
                logger.error(f"Update check raised: {e}", exc_info=True)
                result_holder[0] = {"success": False, "error": str(e)}
            r = result_holder[0] or {}
            print(f"Update check done: success={r.get('success')}, "
                  f"update_available={r.get('update_available')}, error={r.get('error')}",
                  flush=True)
            GLib.idle_add(show_result)

        def show_result():
            """Show the result in the main thread."""
            print("Update check: presenting result window", flush=True)
            progress_dialog.destroy()

            result = result_holder[0]
            if not result or not result.get("success"):
                # Error checking for updates
                error_dialog = Gtk.MessageDialog(
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Update Check Failed"
                )
                error_msg = result.get("error", "Unknown error") if result else "Unknown error"
                error_dialog.format_secondary_text(error_msg)
                error_dialog.set_position(Gtk.WindowPosition.CENTER)
                error_dialog.set_keep_above(True)
                error_dialog.connect("response", lambda d, _r: d.destroy())
                error_dialog.show_all()
                error_dialog.present()
                return

            # Show result dialog
            self._show_update_result_dialog(result)

        # Start background check
        thread = threading.Thread(target=do_check, daemon=True)
        thread.start()

    def _show_update_result_dialog(self, result):
        """Show dialog with update check results.

        Note: GTK tray only shows AppImage updates. Extension updates are handled
        by the GNOME extension menu, which opens Preferences -> Updates tab.
        GTK tray users are either non-GNOME (can't use extension) or GNOME users
        who chose not to install the extension.
        """
        from . import update_checker

        has_update = result.get("update_available", False)
        current = result.get("current_version", "unknown")
        latest = result.get("latest_version", "unknown")
        release = result.get("release", {})

        # How TalkType was installed decides HOW to update. Only a self-managed
        # AppImage can be swapped in place; .deb/.rpm/AUR/Flatpak users must use
        # their package manager, so we show instructions instead of downloading
        # and running an AppImage (which fails, e.g. missing libfuse.so.2).
        install_type = update_checker.get_install_type()
        guidance = update_checker.get_update_guidance(
            install_type, latest, release.get("html_url", ""))

        if not has_update:
            # No AppImage update available
            dialog = Gtk.MessageDialog(
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="You're Up to Date!"
            )
            message = f"<b>TalkType {current}</b> is the latest version."
            dialog.format_secondary_markup(message)
            dialog.set_position(Gtk.WindowPosition.CENTER)
            dialog.set_keep_above(True)
            # Show non-blocking (destroy on response) instead of run(): the tray's GTK
            # loop is in a background thread, and a nested run() loop there can fail to
            # map the dialog on Wayland — the cause of "no result window appears".
            dialog.connect("response", lambda d, _r: d.destroy())
            dialog.show_all()
            dialog.present()
            return

        # Updates available - show detailed dialog
        dialog = Gtk.Dialog(
            title="Update Available",
            flags=Gtk.DialogFlags.MODAL
        )
        dialog.set_default_size(450, 350)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        dialog.set_keep_above(True)

        content = dialog.get_content_area()
        content.set_spacing(10)
        content.set_margin_start(15)
        content.set_margin_end(15)
        content.set_margin_top(15)
        content.set_margin_bottom(10)

        # Header
        header = Gtk.Label()
        header.set_markup("<big><b>Update Available!</b></big>")
        header.set_halign(Gtk.Align.START)
        content.pack_start(header, False, False, 0)

        # Version info
        version_label = Gtk.Label()
        version_label.set_markup(
            f"<b>TalkType:</b> {current} → <b>{latest}</b>"
        )
        version_label.set_halign(Gtk.Align.START)
        content.pack_start(version_label, False, False, 5)

        # For package/AUR/Flatpak installs, explain how to update and show the
        # exact command (selectable so the user can copy it). No auto-download.
        if not guidance["can_auto_update"]:
            how_label = Gtk.Label()
            how_label.set_line_wrap(True)
            how_label.set_halign(Gtk.Align.START)
            how_label.set_markup(guidance["message"])
            content.pack_start(how_label, False, False, 5)
            if guidance.get("command"):
                cmd_entry = Gtk.Entry()
                cmd_entry.set_text(guidance["command"])
                cmd_entry.set_editable(False)
                cmd_entry.get_style_context().add_class("monospace")
                content.pack_start(cmd_entry, False, False, 0)

        # Release notes in scrolled window
        if release.get("body"):
            notes_label = Gtk.Label(label="Release Notes:")
            notes_label.set_halign(Gtk.Align.START)
            notes_label.set_margin_top(10)
            content.pack_start(notes_label, False, False, 0)

            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scroll.set_min_content_height(150)

            notes_text = Gtk.TextView()
            notes_text.set_editable(False)
            notes_text.set_wrap_mode(Gtk.WrapMode.WORD)
            notes_text.set_left_margin(10)
            notes_text.set_right_margin(10)
            notes_text.set_top_margin(10)
            notes_text.get_buffer().set_text(release.get("body", ""))
            scroll.add(notes_text)

            content.pack_start(scroll, True, True, 0)

        # Buttons
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)

        if release.get("html_url"):
            view_btn = dialog.add_button("View on GitHub", Gtk.ResponseType.ACCEPT)

        # Route each install type to the right update action:
        #  appimage_swap  -> download the AppImage and swap it in place
        #  pkexec_package -> download the .rpm/.deb and install it as root
        #  manual         -> just point to the GitHub release page
        method = guidance["update_method"]
        if has_update and method == "appimage_swap" and release.get("appimage_url"):
            btn = dialog.add_button("Download Update", Gtk.ResponseType.YES)
            btn.get_style_context().add_class("suggested-action")
        elif has_update and method == "pkexec_package":
            btn = dialog.add_button("Download & Install", Gtk.ResponseType.APPLY)
            btn.get_style_context().add_class("suggested-action")
        elif has_update and release.get("html_url"):
            view_btn.get_style_context().add_class("suggested-action")

        # Non-blocking (no nested run() loop from the background GTK thread — that can
        # fail to map the window on Wayland). Handle the button response in a callback.
        def _on_update_response(dlg, response):
            if response == Gtk.ResponseType.ACCEPT:
                update_checker.open_release_page(release.get("html_url", ""))
                dlg.destroy()
            elif response == Gtk.ResponseType.YES:
                dlg.destroy()
                self._download_update(release)
            elif response == Gtk.ResponseType.APPLY:
                dlg.destroy()
                self._download_and_install_package(release, install_type)
            else:
                dlg.destroy()
        dialog.connect("response", _on_update_response)
        dialog.show_all()
        dialog.present()

    def _download_update(self, release):
        """Download the update with progress dialog."""
        import threading
        from . import update_checker

        url = release.get("appimage_url")
        filename = release.get("appimage_name", "TalkType-update.AppImage")

        if not url:
            error_dialog = Gtk.MessageDialog(
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Download Error"
            )
            error_dialog.format_secondary_text("Could not find download URL.")
            error_dialog.set_position(Gtk.WindowPosition.CENTER)
            error_dialog.set_keep_above(True)
            error_dialog.run()
            error_dialog.destroy()
            return

        # Create progress dialog
        progress_dialog = Gtk.Dialog(
            title="Downloading Update",
            flags=Gtk.DialogFlags.MODAL
        )
        progress_dialog.set_default_size(400, 120)
        progress_dialog.set_position(Gtk.WindowPosition.CENTER)
        progress_dialog.set_keep_above(True)

        content = progress_dialog.get_content_area()
        content.set_spacing(10)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(10)

        status_label = Gtk.Label(label="Starting download...")
        status_label.set_halign(Gtk.Align.START)
        content.pack_start(status_label, False, False, 0)

        progress_bar = Gtk.ProgressBar()
        progress_bar.set_show_text(True)
        content.pack_start(progress_bar, False, False, 10)

        progress_dialog.show_all()

        result_holder = [None]

        def progress_callback(message, percent):
            """Update progress from background thread."""
            GLib.idle_add(lambda: status_label.set_text(message))
            GLib.idle_add(lambda: progress_bar.set_fraction(percent / 100.0))
            GLib.idle_add(lambda: progress_bar.set_text(f"{percent}%"))

        def do_download():
            """Background thread to download update."""
            result_holder[0] = update_checker.download_update(
                url, filename, progress_callback,
                checksums_url=release.get("checksums_url"))
            GLib.idle_add(download_complete)

        def download_complete():
            """Handle download completion."""
            progress_dialog.destroy()

            downloaded_path = result_holder[0]
            if downloaded_path:
                # Success - automatically install and restart
                # Show brief status dialog
                status_dialog = Gtk.MessageDialog(
                    message_type=Gtk.MessageType.INFO,
                    buttons=Gtk.ButtonsType.NONE,
                    text="Installing Update..."
                )
                status_dialog.format_secondary_text(
                    "TalkType will restart automatically with the new version."
                )
                status_dialog.set_position(Gtk.WindowPosition.CENTER)
                status_dialog.set_keep_above(True)
                status_dialog.show_all()

                # Process events so dialog shows
                while Gtk.events_pending():
                    Gtk.main_iteration()

                # Install and restart (this replaces the current process)
                try:
                    success, message = update_checker.install_update_and_restart(downloaded_path)
                except Exception as install_error:
                    logger.error(f"Exception during install_update_and_restart: {install_error}")
                    success = False
                    message = f"Install failed with exception: {install_error}"

                # Only reach here if install failed (execv didn't work)
                status_dialog.destroy()
                logger.info(f"install_update_and_restart returned: success={success}, message={message}")
                if not success:
                    error_dialog = Gtk.MessageDialog(
                        message_type=Gtk.MessageType.ERROR,
                        buttons=Gtk.ButtonsType.OK,
                        text="Update Failed"
                    )
                    error_dialog.format_secondary_text(message)
                    error_dialog.set_position(Gtk.WindowPosition.CENTER)
                    error_dialog.set_keep_above(True)
                    error_dialog.run()
                    error_dialog.destroy()
            else:
                # Download failed
                error_dialog = Gtk.MessageDialog(
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Download Failed"
                )
                error_dialog.format_secondary_text(
                    "The download could not be completed.\n"
                    "Please try again or download manually from GitHub."
                )
                error_dialog.set_position(Gtk.WindowPosition.CENTER)
                error_dialog.set_keep_above(True)
                error_dialog.run()
                error_dialog.destroy()

        # Start download
        thread = threading.Thread(target=do_download, daemon=True)
        thread.start()

    def _download_and_install_package(self, release, install_type):
        """Download the correct .rpm/.deb and install it as root via pkexec,
        then offer to restart. Delegates to the shared update_ui flow."""
        from . import update_ui
        update_ui.run_package_update(release, install_type)

    def auto_check_for_updates(self):
        """
        Automatically check for updates on startup (once per day).

        Silently checks in the background. If an update is found,
        shows a notification that opens the Updates tab when clicked.
        """
        import threading
        from . import update_checker
        from .config import load_config, save_config

        config = load_config()

        # Check if auto-check is enabled
        if not config.auto_check_updates:
            logger.debug("Auto-update check disabled in config")
            return False

        # Check if we already checked today
        if not update_checker.should_check_today(config.last_update_check):
            logger.debug("Already checked for updates today")
            return False

        logger.info("Auto-checking for updates...")

        def do_check():
            """Background thread to check for updates."""
            try:
                result = update_checker.check_for_updates()

                # Update last check timestamp
                config.last_update_check = update_checker.get_current_timestamp()
                save_config(config)

                if result and result.get("success"):
                    has_update = result.get("update_available", False)
                    has_ext_update = result.get("extension_update", False)

                    if has_update:
                        # Show the SAME actionable dialog the manual check uses
                        # (Download & Install / View on GitHub) — persistent, and
                        # identical across the GTK tray and the GNOME extension.
                        # No surprise Preferences window.
                        GLib.idle_add(lambda: self._show_update_result_dialog(result))
                    elif has_ext_update:
                        # Extension-only update: a quiet notification, no windows.
                        latest = result.get("latest_version", "unknown")
                        GLib.idle_add(lambda: self._show_update_notification(latest, has_update, has_ext_update))
                    else:
                        logger.info("No updates available")
                else:
                    logger.debug(f"Update check failed: {result.get('error', 'unknown')}")
            except Exception as e:
                logger.error(f"Error in auto-update check: {e}")

        # Run in background thread
        thread = threading.Thread(target=do_check, daemon=True)
        thread.start()
        return False  # Don't repeat GLib timeout

    def _show_update_notification(self, latest_version, has_app_update, has_ext_update):
        """Show desktop notification about available update."""
        try:
            import subprocess

            if has_app_update and has_ext_update:
                title = "TalkType Updates Available"
                body = f"TalkType {latest_version} and extension update available"
            elif has_app_update:
                title = "TalkType Update Available"
                body = f"TalkType {latest_version} is now available"
            else:
                title = "Extension Update Available"
                body = "A new GNOME extension version is available"

            # Show notification using notify-send
            subprocess.run([
                "notify-send",
                "--app-name=TalkType",
                "--icon=software-update-available",
                title,
                body + "\nClick 'Check for Updates' in menu for details."
            ], capture_output=True)

            logger.info(f"Showed update notification: {title}")

        except Exception as e:
            logger.error(f"Could not show update notification: {e}")

    def quit_app(self, _):
        """Quit the tray and stop the dictation service."""
        try:
            self._kill_service()
            logger.info("Stopped dictation service")
        except Exception as e:
            logger.error(f"Error stopping dictation service: {e}")

        # Close preferences window if open
        if self.preferences_process and self.preferences_process.poll() is None:
            try:
                self.preferences_process.terminate()
                self.preferences_process.wait(timeout=2)
                logger.info("Closed preferences window")
            except Exception as e:
                logger.error(f"Error closing preferences window: {e}")
                try:
                    self.preferences_process.kill()
                except Exception:
                    pass

        # Clean up D-Bus service if it exists
        if self.dbus_service:
            try:
                # Remove from connection to unregister the service
                self.dbus_service.remove_from_connection()
                logger.info("D-Bus service unregistered")
            except Exception as e:
                logger.error(f"Error unregistering D-Bus service: {e}")
            self.dbus_service = None

        # Quit the GTK main loop
        Gtk.main_quit()

        # Force exit to ensure process terminates
        # Use a small delay to allow GTK cleanup
        GLib.timeout_add(100, lambda: sys.exit(0))
    
    def _build_injection_submenu(self):
        """Build the Text Injection Mode submenu (Auto / Keyboard Typing / Clipboard Paste).

        Stores radio button references on self for later state updates.
        Returns the parent MenuItem that contains the submenu.
        """
        submenu = Gtk.Menu()
        self.injection_mode_group = None

        self.injection_mode_auto = Gtk.RadioMenuItem(label="Auto (Smart Detection)")
        self.injection_mode_auto.connect("activate", lambda w: self.set_injection_mode("auto"))
        submenu.append(self.injection_mode_auto)
        self.injection_mode_group = self.injection_mode_auto

        self.injection_mode_type = Gtk.RadioMenuItem(label="Keyboard Typing", group=self.injection_mode_group)
        self.injection_mode_type.connect("activate", lambda w: self.set_injection_mode("type"))
        submenu.append(self.injection_mode_type)

        self.injection_mode_paste = Gtk.RadioMenuItem(label="Clipboard Paste", group=self.injection_mode_group)
        self.injection_mode_paste.connect("activate", lambda w: self.set_injection_mode("paste"))
        submenu.append(self.injection_mode_paste)

        item = Gtk.MenuItem(label="Text Injection Mode")
        item.set_submenu(submenu)
        return item

    def _build_performance_submenu(self):
        """Build the Performance preset submenu (6 presets + Custom fallback).

        Stores radio button references on self for later state updates.
        Returns the parent MenuItem that contains the submenu.
        """
        submenu = Gtk.Menu()
        self.preset_radios = {}
        preset_group = None

        # Add preset options in order (smallest to largest model, then battery saver)
        preset_order = ["fastest", "light", "balanced", "quality", "accurate", "battery"]
        for preset_id in preset_order:
            preset = self.PERFORMANCE_PRESETS[preset_id]
            label = f"{preset['label']} ({preset['description']})"
            if preset_group is None:
                radio = Gtk.RadioMenuItem(label=label)
                preset_group = radio
            else:
                radio = Gtk.RadioMenuItem(label=label, group=preset_group)
            radio.connect("activate", lambda w, pid=preset_id: self.set_performance_preset(pid))
            submenu.append(radio)
            self.preset_radios[preset_id] = radio

        # "Custom" option (shown when settings don't match any preset)
        submenu.append(Gtk.SeparatorMenuItem())
        self.preset_custom = Gtk.RadioMenuItem(label="Custom (via Preferences)", group=preset_group)
        self.preset_custom.set_sensitive(False)
        submenu.append(self.preset_custom)

        item = Gtk.MenuItem(label="Performance")
        item.set_submenu(submenu)
        return item

    def build_menu(self):
        """Build the complete GTK tray menu.

        Menu order is kept in sync with the GNOME extension (see extension.js).
        """
        menu = Gtk.Menu()

        # Apply dark-theme CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(_MENU_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Service toggle and status displays
        self.service_toggle = Gtk.CheckMenuItem(label="Dictation Service")
        self.service_toggle.connect("toggled", self.toggle_service)
        self.model_display_item = Gtk.MenuItem(label="Active Model: Loading...")
        self.model_display_item.set_sensitive(False)
        self.device_display_item = Gtk.MenuItem(label="Device: Loading...")
        self.device_display_item.set_sensitive(False)

        # Submenus
        self.injection_mode_menu_item = self._build_injection_submenu()
        self.performance_menu_item = self._build_performance_submenu()

        # Service management items
        restart_item = Gtk.MenuItem(label="Restart Service")
        restart_item.connect("activate", self.restart_service)

        # Action items
        prefs_item = Gtk.MenuItem(label="Preferences...")
        voice_cmds_item = Gtk.MenuItem(label="Voice Commands...")
        help_item = Gtk.MenuItem(label="Help...")
        about_item = Gtk.MenuItem(label="About TalkType...")
        updates_item = Gtk.MenuItem(label="Check for Updates...")
        quit_item = Gtk.MenuItem(label="Quit TalkType")
        prefs_item.connect("activate", self.open_preferences)
        voice_cmds_item.connect("activate", self.show_voice_commands)
        help_item.connect("activate", self.show_help)
        about_item.connect("activate", self.show_about_dialog)
        updates_item.connect("activate", self.check_for_updates_clicked)
        quit_item.connect("activate", self.quit_app)

        # Assemble in exact same order as GNOME extension
        for item in [
            self.service_toggle,
            restart_item,
            Gtk.SeparatorMenuItem(),
            self.model_display_item,
            self.device_display_item,
            self.performance_menu_item,
            self.injection_mode_menu_item,
            Gtk.SeparatorMenuItem(),
            prefs_item, voice_cmds_item, help_item, about_item, updates_item,
            Gtk.SeparatorMenuItem(),
            quit_item,
        ]:
            menu.append(item)
        menu.show_all()

        self.update_menu_display()
        return menu
    
    def refresh_menu(self):
        """Rebuild and refresh the tray menu (useful after CUDA installation)."""
        self.indicator.set_menu(self.build_menu())

def _ensure_ydotoold_running():
    """Ensure ydotoold daemon is running for text injection."""
    try:
        # Check if ydotoold is already running
        result = subprocess.run(["pgrep", "-x", "ydotoold"],
                              capture_output=True, text=True)
        if result.returncode == 0:
            logger.debug("ydotoold is already running")
            return

        # Start ydotoold if not running. Don't block startup waiting for it —
        # the daemon comes up within a moment and the first dictation is many
        # seconds away, so the old time.sleep(2) just delayed the tray icon
        # from appearing on every login.
        logger.info("Starting ydotoold daemon for text injection...")
        subprocess.Popen(["ydotoold"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
        logger.info("ydotoold launch requested")
    except FileNotFoundError:
        logger.warning("ydotoold not found in PATH - text injection may not work")
    except Exception as e:
        logger.error(f"Failed to start ydotoold: {e}")

def main():
    _acquire_tray_singleton()

    # Ensure ydotoold is running for text injection
    _ensure_ydotoold_running()

    tray = DictationTray()

    # Check if we just updated and show notification
    def check_and_show_update_notification():
        try:
            from . import update_checker
            from . import __version__
            previous_version = update_checker.check_just_updated()
            if previous_version:
                # Show a brief notification that update completed
                dialog = Gtk.MessageDialog(
                    message_type=Gtk.MessageType.INFO,
                    buttons=Gtk.ButtonsType.OK,
                    text="Update Complete!"
                )
                dialog.format_secondary_markup(
                    f"TalkType has been updated to <b>v{__version__}</b>\n\n"
                    f"The update was installed automatically and "
                    f"TalkType has restarted with the new version."
                )
                dialog.set_position(Gtk.WindowPosition.CENTER)
                dialog.set_keep_above(True)
                dialog.run()
                dialog.destroy()
        except Exception as e:
            logger.debug(f"Error checking for update notification: {e}")
        return False  # Don't repeat

    # Schedule update notification check after tray is up
    GLib.timeout_add(500, check_and_show_update_notification)

    # Check for first run and show welcome dialog if applicable
    try:
        import talktype.cuda_helper as cuda_helper
        from talktype.welcome_dialog import show_welcome_and_install

        # Only show welcome dialog on first tray launch (not for prefs)
        if cuda_helper.is_first_run():
            logger.info("First run detected - starting onboarding")
            # Set flag BEFORE scheduling to prevent any auto-start during onboarding
            tray.onboarding_in_progress = True

            # Kill any existing service that might be running - use SIGKILL for immediate termination
            subprocess.run(["pkill", "-9", "-f", "talktype.app"], capture_output=True)
            subprocess.run(["pkill", "-9", "-f", "bin/dictate"], capture_output=True)
            subprocess.run(["pkill", "-9", "-f", "-m talktype"], capture_output=True)
            time.sleep(0.5)  # Give processes time to die

            # Schedule the welcome dialog after tray is initialized
            def show_first_run_setup():
                # Show unified welcome dialog with all setup options
                result = show_welcome_and_install()

                # Only mark first run complete if user completed the wizard
                if result and result.get('continue'):
                    try:
                        cuda_helper.mark_first_run_complete()
                    except Exception as e:
                        logger.error(f"Failed to mark first run complete: {e}")
                else:
                    logger.info("User cancelled onboarding - will show again next launch")

                # Refresh menu after installations
                tray.refresh_menu()

                # Onboarding complete - NOW allow service to start
                tray.onboarding_in_progress = False
                logger.info("Onboarding complete - starting service")

                # Refresh KDE menu cache so TalkType shows in start menu immediately
                # This must run AFTER the .desktop file is created by the welcome dialog
                try:
                    subprocess.run(["kbuildsycoca6"], capture_output=True, timeout=15)
                    logger.info("KDE menu cache refreshed (kbuildsycoca6)")
                except FileNotFoundError:
                    # Not KDE, try kbuildsycoca5
                    try:
                        subprocess.run(["kbuildsycoca5"], capture_output=True, timeout=15)
                        logger.info("KDE menu cache refreshed (kbuildsycoca5)")
                    except FileNotFoundError:
                        pass  # Not KDE
                except Exception as e:
                    logger.debug(f"Could not refresh KDE menu cache: {e}")

                GLib.timeout_add(500, tray._auto_start_service)
                return False  # Don't repeat

            GLib.timeout_add(1500, show_first_run_setup)  # Show after 1.5 seconds
        else:
            # Not first run, auto-start immediately
            logger.info("Not first run - auto-starting service")
            GLib.timeout_add(1000, tray._auto_start_service)
            # Check for updates after a delay (don't interfere with startup)
            GLib.timeout_add(5000, tray.auto_check_for_updates)
    except Exception as e:
        # If any error, only auto-start if NOT during onboarding
        logger.error(f"Error in first run setup: {e}")
        if not tray.onboarding_in_progress:
            GLib.timeout_add(1000, tray._auto_start_service)

    Gtk.main()

if __name__ == "__main__":
    main()

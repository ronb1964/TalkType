import os
# CRITICAL: Disable HuggingFace XET downloads BEFORE any imports
# XET bypasses tqdm_class progress tracking, breaking our download progress UI
os.environ["HF_HUB_DISABLE_XET"] = "1"

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, AppIndicator3, GLib
import subprocess
import time
import sys
import atexit
import fcntl
from .logger import setup_logger
from .desktop_detect import is_gnome

logger = setup_logger(__name__)

# D-Bus service import (optional - only needed for GNOME extension)
try:
    from .dbus_service import TalkTypeDBusService
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False
    logger.warning("D-Bus service not available - GNOME extension integration disabled")

SERVICE = "talktype.service"  # Not used anymore - we check processes directly

def _runtime_dir():
    return os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

_TRAY_PIDFILE = os.path.join(_runtime_dir(), "talktype-tray.pid")

def _pid_running(pid: int) -> bool:
    if pid <= 0: return False
    proc = f"/proc/{pid}"
    if not os.path.exists(proc): return False
    try:
        with open(os.path.join(proc, "cmdline"), "rb") as f:
            cmd = f.read().decode(errors="ignore")
        return ("talktype.tray" in cmd) or ("dictate-tray" in cmd)
    except Exception:
        return True  # if in doubt, assume running

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

        # Store menu items for dynamic updates
        self.start_item = None
        self.stop_item = None

        # Track subprocess windows
        self.preferences_process = None

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

                def show_preferences(self):
                    """Open preferences via tray."""
                    GLib.idle_add(self.tray.open_preferences, None)

                def show_help(self):
                    """Show help via tray."""
                    GLib.idle_add(self.tray.show_help, None)

                def show_about(self):
                    """Show about dialog via tray."""
                    GLib.idle_add(self.tray.show_about_dialog, None)

                def show_preferences_updates(self):
                    """Open preferences to Updates tab via tray."""
                    GLib.idle_add(self.tray.open_preferences_updates, None)

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
        """Check if the dictation service is active."""
        try:
            # Check both patterns: "talktype.app" (dev) and "bin/dictate" (AppImage)
            result1 = subprocess.run(["pgrep", "-f", "talktype.app"],
                                  capture_output=True, text=True)
            result2 = subprocess.run(["pgrep", "-f", "bin/dictate"],
                                  capture_output=True, text=True)
            return (result1.returncode == 0 and result1.stdout.strip()) or \
                   (result2.returncode == 0 and result2.stdout.strip())
        except Exception:
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

    def update_icon_status(self):
        """Update icon based on service status."""
        if self.is_service_running():
            # Try different icon names for active state
            self.indicator.set_icon_full("microphone-sensitivity-high", "TalkType: Active")
        else:
            # Use muted icon for stopped state
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
    
    def start_service(self, _):
        """Start the dictation service directly."""
        # CRITICAL: Never start service during onboarding - hotkeys must not be active
        if self.onboarding_in_progress:
            logger.info("Onboarding in progress - refusing to start service")
            print("⛔ Service blocked: onboarding in progress")
            return

        try:
            # Find the dictate script relative to this module
            # __file__ is in usr/src/talktype/tray.py
            # dictate is in usr/bin/dictate
            src_dir = os.path.dirname(__file__)  # usr/src/talktype
            usr_dir = os.path.dirname(os.path.dirname(src_dir))  # usr
            dictate_script = os.path.join(usr_dir, "bin", "dictate")

            if os.path.exists(dictate_script):
                # Use the dictate script which has proper paths set up
                subprocess.Popen([dictate_script], env=os.environ.copy())
                logger.info(f"Started dictation service via {dictate_script}")
            else:
                # Fallback: use sys.executable (bundled Python or dev environment)
                # In dev mode, we need to set PYTHONPATH to find the talktype module
                env = os.environ.copy()

                # Check if we're in dev mode (src/talktype structure exists relative to __file__)
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                src_dir_check = os.path.join(project_root, "src")
                if os.path.exists(src_dir_check):
                    # Dev mode - set PYTHONPATH to include src/ AND system PyGObject
                    # Use absolute paths!
                    pythonpath_parts = [
                        os.path.abspath(src_dir_check),
                        "/usr/lib64/python3.14/site-packages",  # System PyGObject on Fedora/Nobara
                        "/usr/lib/python3.14/site-packages"      # Alternative location
                    ]
                    env["PYTHONPATH"] = ":".join(pythonpath_parts)
                    logger.info(f"Dev mode detected - setting PYTHONPATH={env['PYTHONPATH']}")

                subprocess.Popen([sys.executable, "-m", "talktype.app"],
                               env=env)
                logger.info("Started dictation service via Python module")

            # Emit D-Bus signal if available
            if self.dbus_service:
                GLib.timeout_add_seconds(1, lambda: self._emit_service_state_after_check(True))
        except Exception as e:
            print(f"Failed to start service: {e}")
            logger.error(f"Failed to start service: {e}", exc_info=True)
        GLib.timeout_add_seconds(1, self.update_status_and_menu_once)
    
    def stop_service(self, _):
        """Stop the dictation service directly."""
        try:
            # Kill both patterns: "talktype.app" (dev) and "bin/dictate" (AppImage)
            subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
            subprocess.run(["pkill", "-f", "bin/dictate"], capture_output=True)
            logger.info("Stopped dictation service")

            # Emit D-Bus signal if available
            if self.dbus_service:
                GLib.timeout_add_seconds(1, lambda: self._emit_service_state_after_check(False))
        except Exception as e:
            print(f"Failed to stop service: {e}")
            logger.error(f"Failed to stop service: {e}")
        GLib.timeout_add_seconds(1, self.update_status_and_menu_once)
    
    def restart_service(self, _):
        """Restart the dictation service directly."""
        # CRITICAL: Never restart service during onboarding
        if self.onboarding_in_progress:
            logger.info("Onboarding in progress - refusing to restart service")
            print("⛔ Service restart blocked: onboarding in progress")
            return

        try:
            # Stop first - kill both patterns: "talktype.app" (dev) and "bin/dictate" (AppImage)
            subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
            subprocess.run(["pkill", "-f", "bin/dictate"], capture_output=True)
            # Wait a moment for processes to terminate
            time.sleep(1)

            # Find the dictate script relative to this module
            src_dir = os.path.dirname(__file__)  # usr/src/talktype
            usr_dir = os.path.dirname(os.path.dirname(src_dir))  # usr
            dictate_script = os.path.join(usr_dir, "bin", "dictate")

            if os.path.exists(dictate_script):
                # Use the dictate script which has proper paths set up
                subprocess.Popen([dictate_script], env=os.environ.copy())
                logger.info(f"Restarted dictation service via {dictate_script}")
            else:
                # Fallback: use sys.executable (bundled Python)
                subprocess.Popen([sys.executable, "-m", "talktype.app"],
                               env=os.environ.copy())
                logger.info("Restarted dictation service via Python module")
        except Exception as e:
            print(f"Failed to restart service: {e}")
            logger.error(f"Failed to restart service: {e}", exc_info=True)
        GLib.timeout_add_seconds(2, self.update_status_and_menu_once)
    
    def update_status_and_menu(self):
        """Update icon and menu display based on service status."""
        # Store previous state to detect changes
        old_state = getattr(self, '_last_service_state', None)
        new_state = self.is_service_running()

        # Update UI
        self.update_icon_status()
        self.update_menu_display()

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
        return True  # Continue the timer
    
    def update_status_and_menu_once(self):
        """Update icon and menu items once."""
        # Store previous state to detect changes
        old_state = getattr(self, '_last_service_state', None)
        new_state = self.is_service_running()

        # Update UI
        self.update_icon_status()
        self.update_menu_display()

        # If state changed, emit D-Bus signal
        if old_state is not None and old_state != new_state:
            logger.info(f"Service state changed (one-time update): {old_state} -> {new_state}")
            if self.dbus_service:
                try:
                    self.dbus_service.emit_service_state(new_state)
                    logger.debug(f"Emitted D-Bus service state: {new_state}")
                except Exception as e:
                    logger.error(f"Failed to emit D-Bus service state: {e}")

        self._last_service_state = new_state
        return False  # Don't repeat

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
            "device": "cpu"
        }
    }

    def _get_current_preset(self) -> str:
        """
        Determine which preset matches current settings, or 'custom' if none match.
        Match primarily by model - device varies by available hardware.
        """
        try:
            from .config import load_config
            cfg = load_config()

            # First try exact match (model + device)
            for preset_id, preset in self.PERFORMANCE_PRESETS.items():
                if cfg.model == preset["model"] and cfg.device == preset["device"]:
                    return preset_id

            # Fall back to model-only match (device may differ due to hardware)
            for preset_id, preset in self.PERFORMANCE_PRESETS.items():
                if cfg.model == preset["model"]:
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
            from .model_helper import is_model_cached, download_model_with_progress

            # Check if model is cached
            if not is_model_cached(model_name):
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

            # Apply preset settings
            cfg.model = preset["model"]
            cfg.device = preset["device"]

            # Battery saver also reduces timeout
            if preset_id == "battery":
                cfg.auto_timeout_enabled = True
                cfg.auto_timeout_minutes = 2  # Shorter timeout for battery saving

            # Save config
            save_config(cfg)

            # Notify user
            from .app import _notify
            logger.info(f"Applied performance preset: {preset['label']}")
            _notify("TalkType", f"Performance: {preset['label']}\nRestarting service...")

            # Update menu display
            self.update_menu_display()

            # Restart service to apply new model
            self.restart_service(None)

        except Exception as e:
            logger.error(f"Failed to apply performance preset: {e}")

    def update_menu_display(self):
        """Update menu display with current service status and model."""
        if hasattr(self, 'service_toggle'):
            # Update service toggle state
            is_running = self.is_service_running()
            self._updating_toggle = True
            self.service_toggle.set_active(is_running)
            self._updating_toggle = False

        # Update active model display
        if hasattr(self, 'model_display_item'):
            try:
                from .config import load_config, CONFIG_PATH
                cfg = load_config()
                # Debug: print config values every 10 seconds (not every update)
                if not hasattr(self, '_debug_counter'):
                    self._debug_counter = 0
                self._debug_counter += 1
                if self._debug_counter % 10 == 1:  # Every ~10 seconds
                    logger.debug(f"Config read from {CONFIG_PATH}: model={cfg.model}, device={cfg.device}")
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
    
    def open_preferences(self, _):
        """Launch preferences window."""
        try:
            # Check if preferences is already open
            if self.preferences_process and self.preferences_process.poll() is None:
                logger.info("Preferences window already open")
                return

            # Find the dictate-prefs script relative to this module (AppImage path)
            # __file__ is in usr/src/talktype/tray.py
            # dictate-prefs is in usr/bin/dictate-prefs
            src_dir = os.path.dirname(__file__)  # usr/src/talktype
            usr_dir = os.path.dirname(os.path.dirname(src_dir))  # usr
            prefs_script = os.path.join(usr_dir, "bin", "dictate-prefs")

            if os.path.exists(prefs_script):
                # Use the dictate-prefs script which has proper paths set up (AppImage)
                self.preferences_process = subprocess.Popen([prefs_script], env=os.environ.copy())
                logger.info(f"Opened preferences window via {prefs_script}")
            else:
                # Fallback: use sys.executable (dev environment)
                env = os.environ.copy()

                # Check if we're in dev mode (src/talktype structure exists relative to __file__)
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                src_dir_check = os.path.join(project_root, "src")
                if os.path.exists(src_dir_check):
                    # Dev mode - set PYTHONPATH to include src/ AND system PyGObject
                    pythonpath_parts = [
                        os.path.abspath(src_dir_check),
                        "/usr/lib64/python3.14/site-packages",
                        "/usr/lib/python3.14/site-packages",
                        "/usr/lib64/python3.13/site-packages",
                        "/usr/lib/python3.13/site-packages"
                    ]
                    env["PYTHONPATH"] = ":".join(pythonpath_parts)
                    logger.info(f"Dev mode detected - setting PYTHONPATH for prefs")

                self.preferences_process = subprocess.Popen(
                    [sys.executable, "-m", "talktype.prefs"],
                    env=env
                )
                logger.info("Opened preferences window via Python module")
        except Exception as e:
            logger.error(f"Failed to open preferences: {e}")
            print(f"Failed to open preferences: {e}")

    def open_preferences_updates(self, _):
        """Launch preferences window directly to Updates tab."""
        try:
            # Check if preferences is already open
            if self.preferences_process and self.preferences_process.poll() is None:
                logger.info("Preferences window already open")
                return

            # Find the dictate-prefs script relative to this module (AppImage path)
            src_dir = os.path.dirname(__file__)
            usr_dir = os.path.dirname(os.path.dirname(src_dir))
            prefs_script = os.path.join(usr_dir, "bin", "dictate-prefs")

            if os.path.exists(prefs_script):
                # Use the dictate-prefs script with --tab argument
                self.preferences_process = subprocess.Popen(
                    [prefs_script, "--tab=updates"],
                    env=os.environ.copy()
                )
                logger.info(f"Opened preferences Updates tab via {prefs_script}")
            else:
                # Fallback: use sys.executable (dev environment)
                env = os.environ.copy()

                # Check if we're in dev mode
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                src_dir_check = os.path.join(project_root, "src")
                if os.path.exists(src_dir_check):
                    pythonpath_parts = [
                        os.path.abspath(src_dir_check),
                        "/usr/lib64/python3.14/site-packages",
                        "/usr/lib/python3.14/site-packages",
                        "/usr/lib64/python3.13/site-packages",
                        "/usr/lib/python3.13/site-packages"
                    ]
                    env["PYTHONPATH"] = ":".join(pythonpath_parts)

                self.preferences_process = subprocess.Popen(
                    [sys.executable, "-m", "talktype.prefs", "--tab=updates"],
                    env=env
                )
                logger.info("Opened preferences Updates tab via Python module")
        except Exception as e:
            logger.error(f"Failed to open preferences updates tab: {e}")
            print(f"Failed to open preferences updates tab: {e}")

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
            "This will download approximately 800MB of CUDA libraries for GPU acceleration.\n\n"
            f"The files will be stored in {cuda_path} and may take several minutes to download.\n\n"
            "Continue with download?"
        )
        confirm_dialog.set_position(Gtk.WindowPosition.CENTER)
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
                except Exception as save_e:
                    logger.warning(f"Could not auto-enable GPU mode: {save_e}")
            else:
                logger.error("CUDA download failed")
        except Exception as e:
            print(f"Error downloading CUDA: {e}")
            logger.error(f"Error downloading CUDA: {e}")
    
    def show_help(self, _):
        """Show help dialog with TalkType features and instructions."""
        from .help_dialog import show_help_dialog
        show_help_dialog()

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
        progress_dialog.show_all()

        result_holder = [None]

        def do_check():
            """Background thread to check for updates."""
            result_holder[0] = update_checker.check_for_updates()
            GLib.idle_add(show_result)

        def show_result():
            """Show the result in the main thread."""
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
                error_dialog.run()
                error_dialog.destroy()
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
            dialog.run()
            dialog.destroy()
            return

        # Updates available - show detailed dialog
        dialog = Gtk.Dialog(
            title="Update Available",
            flags=Gtk.DialogFlags.MODAL
        )
        dialog.set_default_size(450, 350)
        dialog.set_position(Gtk.WindowPosition.CENTER)

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

        if has_update and release.get("appimage_url"):
            download_btn = dialog.add_button("Download Update", Gtk.ResponseType.YES)
            download_btn.get_style_context().add_class("suggested-action")

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.ACCEPT:
            # Open GitHub release page
            update_checker.open_release_page(release.get("html_url", ""))
        elif response == Gtk.ResponseType.YES:
            # Download update
            dialog.destroy()
            self._download_update(release)
            return

        dialog.destroy()

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
            result_holder[0] = update_checker.download_update(url, filename, progress_callback)
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
                error_dialog.run()
                error_dialog.destroy()

        # Start download
        thread = threading.Thread(target=do_download, daemon=True)
        thread.start()

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

                    if has_update or has_ext_update:
                        # Update available - show notification
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

            # Also open preferences to Updates tab automatically
            self.open_preferences_updates(None)

        except Exception as e:
            logger.error(f"Could not show update notification: {e}")

    def quit_app(self, _):
        """Quit the tray and stop the dictation service."""
        try:
            # Stop the dictation service first - kill both patterns
            subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
            subprocess.run(["pkill", "-f", "bin/dictate"], capture_output=True)
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
                except:
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
    
    def build_menu(self):
        menu = Gtk.Menu()

        # Apply custom CSS for better readability (solid dark background)
        css_provider = Gtk.CssProvider()
        css = b"""
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
        css_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        
        # Dictation Service toggle (using CheckMenuItem for ON/OFF display)
        self.service_toggle = Gtk.CheckMenuItem(label="Dictation Service")
        self.service_toggle.connect("toggled", self.toggle_service)

        # Active model display (non-clickable)
        self.model_display_item = Gtk.MenuItem(label="Active Model: Loading...")
        self.model_display_item.set_sensitive(False)

        # Device mode display (non-clickable)
        self.device_display_item = Gtk.MenuItem(label="Device: Loading...")
        self.device_display_item.set_sensitive(False)

        # Injection mode submenu (Auto / Keyboard Typing / Clipboard Paste)
        injection_mode_submenu = Gtk.Menu()
        self.injection_mode_group = None
        
        self.injection_mode_auto = Gtk.RadioMenuItem(label="Auto (Smart Detection)")
        self.injection_mode_auto.connect("activate", lambda w: self.set_injection_mode("auto"))
        injection_mode_submenu.append(self.injection_mode_auto)
        self.injection_mode_group = self.injection_mode_auto
        
        self.injection_mode_type = Gtk.RadioMenuItem(label="Keyboard Typing", group=self.injection_mode_group)
        self.injection_mode_type.connect("activate", lambda w: self.set_injection_mode("type"))
        injection_mode_submenu.append(self.injection_mode_type)
        
        self.injection_mode_paste = Gtk.RadioMenuItem(label="Clipboard Paste", group=self.injection_mode_group)
        self.injection_mode_paste.connect("activate", lambda w: self.set_injection_mode("paste"))
        injection_mode_submenu.append(self.injection_mode_paste)
        
        self.injection_mode_menu_item = Gtk.MenuItem(label="Text Injection Mode")
        self.injection_mode_menu_item.set_submenu(injection_mode_submenu)

        # Performance preset submenu
        performance_submenu = Gtk.Menu()
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
            performance_submenu.append(radio)
            self.preset_radios[preset_id] = radio

        # Add separator and "Custom" option (shown when settings don't match any preset)
        performance_submenu.append(Gtk.SeparatorMenuItem())
        self.preset_custom = Gtk.RadioMenuItem(label="Custom (via Preferences)", group=preset_group)
        self.preset_custom.set_sensitive(False)  # Can't select - just shows current state
        performance_submenu.append(self.preset_custom)

        self.performance_menu_item = Gtk.MenuItem(label="Performance")
        self.performance_menu_item.set_submenu(performance_submenu)

        # Menu items
        prefs_item = Gtk.MenuItem(label="Preferences...")
        help_item = Gtk.MenuItem(label="Help...")
        about_item = Gtk.MenuItem(label="About TalkType...")
        updates_item = Gtk.MenuItem(label="Check for Updates...")
        quit_item = Gtk.MenuItem(label="Quit TalkType")

        prefs_item.connect("activate", self.open_preferences)
        help_item.connect("activate", self.show_help)
        about_item.connect("activate", self.show_about_dialog)
        updates_item.connect("activate", self.check_for_updates_clicked)
        quit_item.connect("activate", self.quit_app)

        # Build menu in exact same order as extension
        menu_items = [
            self.service_toggle,
            Gtk.SeparatorMenuItem(),
            self.model_display_item,
            self.device_display_item,
            self.performance_menu_item,
            self.injection_mode_menu_item,
            Gtk.SeparatorMenuItem(),
            prefs_item,
            help_item,
            about_item,
            updates_item,
            Gtk.SeparatorMenuItem(),
            quit_item
        ]

        for item in menu_items:
            menu.append(item)
        menu.show_all()

        # Set initial menu state
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

        # Start ydotoold if not running
        logger.info("Starting ydotoold daemon for text injection...")
        subprocess.Popen(["ydotoold"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
        time.sleep(2)  # Give it time to start
        logger.info("ydotoold started successfully")
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

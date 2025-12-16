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
            # Check for running talktype.app process
            result = subprocess.run(["pgrep", "-f", "talktype.app"],
                                  capture_output=True, text=True)
            return result.returncode == 0 and result.stdout.strip()
        except Exception:
            return False

    def _auto_start_service(self):
        """Auto-start the dictation service if not already running."""
        try:
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
            subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
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
        try:
            # Stop first
            subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
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
        """
        try:
            from .config import load_config
            cfg = load_config()

            for preset_id, preset in self.PERFORMANCE_PRESETS.items():
                if cfg.model == preset["model"] and cfg.device == preset["device"]:
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

    def quit_app(self, _):
        """Quit the tray and stop the dictation service."""
        try:
            # Stop the dictation service first
            subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
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
        quit_item = Gtk.MenuItem(label="Quit TalkType")

        prefs_item.connect("activate", self.open_preferences)
        help_item.connect("activate", self.show_help)
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
    
    # Check for first run and show welcome dialog if applicable
    try:
        import talktype.cuda_helper as cuda_helper
        from talktype.welcome_dialog import show_welcome_and_install

        # Only show welcome dialog on first tray launch (not for prefs)
        if cuda_helper.is_first_run():
            # Schedule the welcome dialog after tray is initialized
            def show_first_run_setup():
                # Show unified welcome dialog with all setup options
                show_welcome_and_install()

                # Mark first run as complete
                try:
                    cuda_helper.mark_first_run_complete()
                except Exception as e:
                    logger.error(f"Failed to mark first run complete: {e}")

                # Refresh menu after installations
                tray.refresh_menu()

                # NOW start the service (after welcome dialog)
                GLib.timeout_add(500, tray._auto_start_service)
                return False  # Don't repeat

            GLib.timeout_add(1500, show_first_run_setup)  # Show after 1.5 seconds
        else:
            # Not first run, auto-start immediately
            GLib.timeout_add(1000, tray._auto_start_service)
    except Exception as e:
        # If any error, still try to auto-start
        logger.error(f"Error in first run setup: {e}")
        GLib.timeout_add(1000, tray._auto_start_service)
    
    Gtk.main()

if __name__ == "__main__":
    main()

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
import os
import subprocess
import sys
import atexit
from .config import CONFIG_PATH

# Use tomllib (Python 3.11+) or fallback to toml
try:
    import tomllib
    def load_toml(path):
        with open(path, "rb") as f:
            return tomllib.load(f)
except ImportError:
    try:
        import toml
        def load_toml(path):
            with open(path, "r") as f:
                return toml.load(f)
    except ImportError:
        def load_toml(path):
            # Basic fallback parser
            config = {}
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if value.lower() in ("true", "false"):
                            config[key] = value.lower() == "true"
                        else:
                            config[key] = value
            return config

# Single instance management
def _runtime_dir():
    return os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

_PREFS_PIDFILE = os.path.join(_runtime_dir(), "talktype-prefs.pid")

def _pid_running(pid: int) -> bool:
    if pid <= 0: return False
    proc = f"/proc/{pid}"
    if not os.path.exists(proc): return False
    try:
        with open(os.path.join(proc, "cmdline"), "rb") as f:
            cmd = f.read().decode(errors="ignore")
        return ("dictate-prefs" in cmd) or ("talktype.prefs" in cmd)
    except Exception:
        return True

def _acquire_prefs_singleton():
    try:
        if os.path.exists(_PREFS_PIDFILE):
            try:
                with open(_PREFS_PIDFILE, "r") as f:
                    old = int(f.read().strip() or "0")
            except Exception:
                old = 0
            if _pid_running(old):
                print("Another preferences window is already open. Exiting.")
                sys.exit(0)
        with open(_PREFS_PIDFILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        print(f"Warning: could not write prefs pidfile: {e}")
    def _cleanup():
        try:
            with open(_PREFS_PIDFILE, "r") as f:
                cur = int(f.read().strip() or "0")
            if cur == os.getpid():
                os.remove(_PREFS_PIDFILE)
        except Exception:
            pass
    atexit.register(_cleanup)

class PreferencesWindow:
    def __init__(self):
        self.window = Gtk.Window(title="TalkType Preferences")
        self.window.set_default_size(500, 400)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        
        # Load current config
        self.config = self.load_config()
        
        # Create UI
        self.create_ui()
        
        # Connect window close event to cleanup
        self.window.connect("delete-event", self.on_window_close)
        
        # Show window - force it to appear
        self.window.show_all()
        self.window.present()  # Bring window to front
        self.window.set_keep_above(True)  # Force window on top temporarily
        GLib.timeout_add_seconds(1, self._remove_keep_above)  # Remove keep_above after 1 second
        
    def load_config(self):
        """Load config from TOML file."""
        defaults = {
            "model": "tiny",
            "device": "cpu", 
            "hotkey": "F8",
            "beeps": True,
            "smart_quotes": True,
            "mode": "hold",
            "toggle_hotkey": "F9",
            "mic": "",
            "notify": True,
            "language": "en",
            "auto_space": True,
            "auto_period": True,
            "paste_injection": True,
            "injection_mode": "paste"
        }
        
        if os.path.exists(CONFIG_PATH):
            try:
                config = load_toml(CONFIG_PATH)
                defaults.update(config)
            except Exception as e:
                print(f"Error loading config: {e}")
        
        return defaults
    
    def _remove_keep_above(self):
        """Remove keep_above setting after window appears."""
        self.window.set_keep_above(False)
        return False  # Don't repeat
    
    def _check_cuda_availability(self):
        """Check if CUDA is available for faster-whisper."""
        try:
            from faster_whisper import WhisperModel
            # Try to create a tiny model with CUDA - this will fail if CUDA isn't available
            model = WhisperModel("tiny", device="cuda")
            del model  # Clean up
            return True
        except Exception:
            return False
    
    def save_config(self):
        """Save config to TOML file."""
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                f.write("# TalkType config\n")
                for key, value in self.config.items():
                    if isinstance(value, str):
                        f.write(f'{key} = "{value}"\n')
                    elif isinstance(value, bool):
                        f.write(f'{key} = {str(value).lower()}\n')
                    else:
                        f.write(f'{key} = {value}\n')
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def create_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        # Use newer margin methods to avoid deprecation warnings
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>TalkType Preferences</b></big>")
        vbox.pack_start(title, False, False, 0)
        
        # Notebook for tabs
        notebook = Gtk.Notebook()
        
        # General tab
        general_tab = self.create_general_tab()
        notebook.append_page(general_tab, Gtk.Label(label="General"))
        
        # Audio tab  
        audio_tab = self.create_audio_tab()
        notebook.append_page(audio_tab, Gtk.Label(label="Audio"))
        
        # Advanced tab
        advanced_tab = self.create_advanced_tab()
        notebook.append_page(advanced_tab, Gtk.Label(label="Advanced"))
        
        vbox.pack_start(notebook, True, True, 0)
        
        # Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", self.on_cancel)
        
        apply_btn = Gtk.Button(label="Apply")
        apply_btn.connect("clicked", self.on_apply)
        
        ok_btn = Gtk.Button(label="OK")
        ok_btn.connect("clicked", self.on_ok)
        ok_btn.set_can_default(True)
        ok_btn.grab_default()
        
        button_box.pack_start(cancel_btn, False, False, 0)
        button_box.pack_start(apply_btn, False, False, 0)
        button_box.pack_start(ok_btn, False, False, 0)
        
        vbox.pack_start(button_box, False, False, 0)
        self.window.add(vbox)
    
    def create_general_tab(self):
        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(10)
        grid.set_margin_start(20)
        grid.set_margin_end(20)
        grid.set_margin_top(20)
        grid.set_margin_bottom(20)
        
        row = 0
        
        # Model selection
        grid.attach(Gtk.Label(label="Model:", xalign=0), 0, row, 1, 1)
        model_combo = Gtk.ComboBoxText()
        
        # Fix dropdown responsiveness - enable proper focus handling
        model_combo.set_can_focus(True)
        # Add button press event to ensure dropdown opens reliably
        model_combo.connect("button-press-event", self._on_combo_button_press)
        
        models = ["tiny", "base", "small", "medium", "large-v3"]
        for model in models:
            model_combo.append(model, model)  # append(id, text) - use model name as both ID and text
        model_combo.set_active_id(self.config["model"])
        model_combo.connect("changed", lambda x: self.update_config("model", x.get_active_id()))
        model_combo.set_tooltip_text("Whisper AI model size. Larger models are more accurate but slower:\n• tiny: fastest, least accurate\n• small: good balance (recommended)\n• large-v3: most accurate, slowest")
        grid.attach(model_combo, 1, row, 1, 1)
        row += 1
        
        # Device selection
        grid.attach(Gtk.Label(label="Device:", xalign=0), 0, row, 1, 1)
        device_combo = Gtk.ComboBoxText()
        
        # Fix dropdown responsiveness - enable proper focus handling
        device_combo.set_can_focus(True)
        # Add button press event to ensure dropdown opens reliably
        device_combo.connect("button-press-event", self._on_combo_button_press)
        
        device_combo.append("cpu", "CPU")
        
        # Only add CUDA option if it's actually available
        cuda_available = self._check_cuda_availability()
        if cuda_available:
            device_combo.append("cuda", "CUDA (GPU)")
            tooltip_text = "Processing device for AI transcription:\n• CPU: works on all computers, slower\n• CUDA (GPU): much faster, requires NVIDIA graphics card"
        else:
            tooltip_text = "Processing device for AI transcription:\n• CPU: works on all computers\n• CUDA: not available (no NVIDIA GPU or missing CUDA libraries)"
            # If config has CUDA but it's not available, reset to CPU
            if self.config["device"] == "cuda":
                self.config["device"] = "cpu"
        
        device_combo.set_active_id(self.config["device"])
        device_combo.connect("changed", lambda x: self.update_config("device", x.get_active_id()))
        device_combo.set_tooltip_text(tooltip_text)
        grid.attach(device_combo, 1, row, 1, 1)
        row += 1
        
        # Language Mode
        grid.attach(Gtk.Label(label="Language Mode:", xalign=0), 0, row, 1, 1)
        language_mode_combo = Gtk.ComboBoxText()
        language_mode_combo.append("auto", "Auto-detect")
        language_mode_combo.append("manual", "Manual")
        language_mode_combo.set_active_id(self.config.get("language_mode", "auto"))
        language_mode_combo.connect("changed", lambda x: self.update_config("language_mode", x.get_active_id()))
        grid.attach(language_mode_combo, 1, row, 1, 1)
        row += 1
        
        # Language
        grid.attach(Gtk.Label(label="Language:", xalign=0), 0, row, 1, 1)
        lang_entry = Gtk.Entry()
        lang_entry.set_text(self.config["language"])
        lang_entry.set_placeholder_text("e.g., 'en' or leave empty for auto-detect")
        lang_entry.connect("changed", lambda x: self.update_config("language", x.get_text()))
        grid.attach(lang_entry, 1, row, 1, 1)
        row += 1
        
        # Mode selection
        grid.attach(Gtk.Label(label="Mode:", xalign=0), 0, row, 1, 1)
        mode_combo = Gtk.ComboBoxText()
        
        # Fix dropdown responsiveness - enable proper focus handling
        mode_combo.set_can_focus(True)
        # Add button press event to ensure dropdown opens reliably
        mode_combo.connect("button-press-event", self._on_combo_button_press)
        
        mode_combo.append("hold", "Hold to Talk")
        mode_combo.append("toggle", "Press to Toggle")
        mode_combo.set_active_id(self.config["mode"])
        mode_combo.connect("changed", lambda x: self.update_config("mode", x.get_active_id()))
        mode_combo.set_tooltip_text("How to activate dictation:\n• Hold to Talk: hold hotkey down while speaking\n• Press to Toggle: press once to start, press again to stop")
        grid.attach(mode_combo, 1, row, 1, 1)
        row += 1
        
        # Hotkey
        grid.attach(Gtk.Label(label="Hold Hotkey:", xalign=0), 0, row, 1, 1)
        hotkey_combo = Gtk.ComboBoxText()
        
        # Fix dropdown responsiveness - enable proper focus handling
        hotkey_combo.set_can_focus(True)
        # Add button press event to ensure dropdown opens reliably
        hotkey_combo.connect("button-press-event", self._on_combo_button_press)
        
        # Add F-key options (most practical for dictation)
        hotkeys = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"]
        
        for key in hotkeys:
            hotkey_combo.append(key, key)
        
        # Set current selection or default to F8
        current_hotkey = self.config.get("hotkey", "F8")
        if current_hotkey in hotkeys:
            hotkey_combo.set_active_id(current_hotkey)
        else:
            hotkey_combo.set_active_id("F8")  # Default fallback
            
        hotkey_combo.connect("changed", lambda x: self.update_config("hotkey", x.get_active_id()))
        hotkey_combo.set_tooltip_text("Choose the key to hold down for dictation.\nRecommended: F8 (default), F6, F7, F9, F10\nAvoid: F1 (help), F5 (refresh), F11 (fullscreen), F12 (dev tools)")
        grid.attach(hotkey_combo, 1, row, 1, 1)
        row += 1
        
        # Toggle hotkey
        grid.attach(Gtk.Label(label="Toggle Hotkey:", xalign=0), 0, row, 1, 1)
        toggle_combo = Gtk.ComboBoxText()
        
        # Fix dropdown responsiveness - enable proper focus handling
        toggle_combo.set_can_focus(True)
        # Add button press event to ensure dropdown opens reliably
        toggle_combo.connect("button-press-event", self._on_combo_button_press)
        
        # Add same options for toggle key
        for key in hotkeys:
            toggle_combo.append(key, key)
            
        # Set current selection or default to F9
        current_toggle = self.config.get("toggle_hotkey", "F9")
        if current_toggle in hotkeys:
            toggle_combo.set_active_id(current_toggle)
        else:
            toggle_combo.set_active_id("F9")  # Default fallback
            
        toggle_combo.connect("changed", lambda x: self.update_config("toggle_hotkey", x.get_active_id()))
        toggle_combo.set_tooltip_text("Choose the key for toggle mode (press once to start, press again to stop).\nRecommended: F9 (default), F10, F6, F7\nOnly used when Mode is set to 'Press to Toggle'.")
        grid.attach(toggle_combo, 1, row, 1, 1)
        row += 1
        
        # Launch at Login
        launch_check = Gtk.CheckButton(label="Launch at login")
        launch_check.set_active(self.config.get("launch_at_login", False))
        launch_check.connect("toggled", lambda x: self.update_config("launch_at_login", x.get_active()))
        launch_check.set_tooltip_text("Automatically start TalkType when you log in to your desktop.")
        grid.attach(launch_check, 0, row, 2, 1)
        row += 1
        
        return grid
    
    def create_audio_tab(self):
        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(10)
        grid.set_margin_start(20)
        grid.set_margin_end(20)
        grid.set_margin_top(20)
        grid.set_margin_bottom(20)
        
        row = 0
        
        # Microphone
        grid.attach(Gtk.Label(label="Microphone:", xalign=0), 0, row, 1, 1)
        mic_combo = Gtk.ComboBoxText()
        
        # Fix dropdown responsiveness - enable proper focus handling
        mic_combo.set_can_focus(True)
        # Add button press event to ensure dropdown opens reliably
        mic_combo.connect("button-press-event", self._on_combo_button_press)
        
        # Get available input devices
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            input_devices = [(i, d) for i, d in enumerate(devices) if d.get("max_input_channels", 0) > 0]
            
            # Add default option
            mic_combo.append("", "System Default")
            
            # Add all input devices
            for device_idx, device_info in input_devices:
                device_name = device_info.get("name", f"Device {device_idx}")
                # Use device name as ID for matching
                mic_combo.append(device_name, f"{device_name}")
                
        except Exception as e:
            # Fallback if sounddevice fails
            mic_combo.append("", "System Default")
            print(f"Could not list audio devices: {e}")
        
        # Set current selection
        current_mic = self.config["mic"]
        if not current_mic:
            mic_combo.set_active_id("")  # Default
        else:
            # Try to find matching device
            mic_combo.set_active_id(current_mic)
            if mic_combo.get_active_id() is None:
                # If exact match not found, set to default
                mic_combo.set_active_id("")
        
        mic_combo.connect("changed", lambda x: self.update_config("mic", x.get_active_id()))
        grid.attach(mic_combo, 1, row, 1, 1)
        row += 1
        
        # Beeps
        beeps_check = Gtk.CheckButton(label="Play beeps for start/stop/ready")
        beeps_check.set_active(self.config["beeps"])
        beeps_check.connect("toggled", lambda x: self.update_config("beeps", x.get_active()))
        beeps_check.set_tooltip_text("Play audio beeps to confirm when recording starts, stops, and when transcription is ready.\nHelps you know the system is responding.")
        grid.attach(beeps_check, 0, row, 2, 1)
        row += 1
        
        # Notifications
        notify_check = Gtk.CheckButton(label="Show desktop notifications")
        notify_check.set_active(self.config["notify"])
        notify_check.connect("toggled", lambda x: self.update_config("notify", x.get_active()))
        notify_check.set_tooltip_text("Show desktop notifications with transcribed text preview.\nUseful to confirm what was transcribed without switching windows.")
        grid.attach(notify_check, 0, row, 2, 1)
        row += 1
        
        # Microphone Testing Section
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        grid.attach(separator, 0, row, 2, 1)
        row += 1
        
        # Microphone Test Label
        test_label = Gtk.Label(label="Microphone Test")
        test_label.set_markup("<b>Microphone Test</b>")
        test_label.set_xalign(0)
        grid.attach(test_label, 0, row, 2, 1)
        row += 1
        
        # Test Recording Button
        self.record_button = Gtk.Button(label="Start Recording")
        self.record_button.connect("clicked", self.on_record_clicked)
        self.record_button.set_tooltip_text("Test your microphone by recording a short sample")
        grid.attach(self.record_button, 0, row, 1, 1)
        
        # Level indicator
        self.level_bar = Gtk.LevelBar()
        self.level_bar.set_min_value(0.0)
        self.level_bar.set_max_value(1.0)
        self.level_bar.set_tooltip_text("Microphone input level")
        grid.attach(self.level_bar, 1, row, 1, 1)
        row += 1
        
        return grid
    
    def create_advanced_tab(self):
        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(10)
        grid.set_margin_start(20)
        grid.set_margin_end(20)
        grid.set_margin_top(20)
        grid.set_margin_bottom(20)
        
        row = 0
        
        # Smart quotes
        quotes_check = Gtk.CheckButton(label="Use smart quotes (" ")")
        quotes_check.set_active(self.config["smart_quotes"])
        quotes_check.connect("toggled", lambda x: self.update_config("smart_quotes", x.get_active()))
        quotes_check.set_tooltip_text("Convert spoken quotes to curved 'smart quotes' instead of straight \"quotes\".\nSay 'open quote' and 'close quote' when dictating.")
        grid.attach(quotes_check, 0, row, 2, 1)
        row += 1
        
        # Auto space
        space_check = Gtk.CheckButton(label="Auto-space between utterances")
        space_check.set_active(self.config["auto_space"])
        space_check.connect("toggled", lambda x: self.update_config("auto_space", x.get_active()))
        space_check.set_tooltip_text("Automatically add a space before each new dictation.\nTurn off if you want to control spacing manually.")
        grid.attach(space_check, 0, row, 2, 1)
        row += 1
        
        # Auto period
        period_check = Gtk.CheckButton(label="Auto-add period at end of sentences")
        period_check.set_active(self.config["auto_period"])
        period_check.connect("toggled", lambda x: self.update_config("auto_period", x.get_active()))
        period_check.set_tooltip_text("Automatically add a period at the end if your sentence doesn't end with punctuation.\nUseful for quick note-taking.")
        grid.attach(period_check, 0, row, 2, 1)
        row += 1
        
        # Injection mode
        grid.attach(Gtk.Label(label="Text Injection:", xalign=0), 0, row, 1, 1)
        inject_combo = Gtk.ComboBoxText()
        
        # Fix dropdown responsiveness - enable proper focus handling
        inject_combo.set_can_focus(True)
        # Add button press event to ensure dropdown opens reliably
        inject_combo.connect("button-press-event", self._on_combo_button_press)
        
        inject_combo.append("type", "Keystroke Typing")
        inject_combo.append("paste", "Clipboard Paste")
        inject_combo.set_active_id(self.config["injection_mode"])
        inject_combo.connect("changed", lambda x: self.update_config("injection_mode", x.get_active_id()))
        inject_combo.set_tooltip_text("How to insert transcribed text:\n• Keystroke Typing: simulates typing (more reliable)\n• Clipboard Paste: uses copy/paste (faster for long text)")
        grid.attach(inject_combo, 1, row, 1, 1)
        row += 1
        
        return grid
    
    def update_config(self, key, value):
        """Update config value."""
        self.config[key] = value
    
    def _on_combo_button_press(self, widget, event):
        """Handle button press events on combo boxes to ensure they open reliably."""
        # Ensure the widget has focus before processing the click
        if not widget.has_focus():
            widget.grab_focus()
        # Let GTK handle the normal click event
        return False
    
    def on_window_close(self, widget, event):
        """Handle window close event to clean up PID file."""
        try:
            with open(_PREFS_PIDFILE, "r") as f:
                cur = int(f.read().strip() or "0")
            if cur == os.getpid():
                os.remove(_PREFS_PIDFILE)
        except Exception:
            pass
        Gtk.main_quit()
        return False
    
    def restart_service(self):
        """Restart the dictation service."""
        try:
            import subprocess
            # Don't use systemctl - restart the process directly
            subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
            # Wait a moment for processes to terminate
            import time
            time.sleep(1)
            # Start the service again using the same Python interpreter as the preferences
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            python_path = sys.executable
            subprocess.Popen([python_path, "-m", "src.talktype.app"], 
                           cwd=project_dir, 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            result = subprocess.run(["true"], 
                                  capture_output=True, text=True)
            return result.returncode == 0
        except Exception:
            return False
    
    def on_apply(self, button):
        """Apply changes and restart service without closing."""
        if self.save_config():
            # Restart the service
            if self.restart_service():
                # Show confirmation
                dialog = Gtk.MessageDialog(
                    transient_for=self.window,
                    flags=0,
                    message_type=Gtk.MessageType.INFO,
                    buttons=Gtk.ButtonsType.OK,
                    text="Settings applied successfully!"
                )
                dialog.format_secondary_text("Dictation service has been restarted with new settings.")
                dialog.run()
                dialog.destroy()
            else:
                # Show service restart error
                dialog = Gtk.MessageDialog(
                    transient_for=self.window,
                    flags=0,
                    message_type=Gtk.MessageType.WARNING,
                    buttons=Gtk.ButtonsType.OK,
                    text="Settings saved, but service restart failed!"
                )
                dialog.format_secondary_text("You may need to manually restart the service.")
                dialog.run()
                dialog.destroy()
        else:
            # Show save error
            dialog = Gtk.MessageDialog(
                transient_for=self.window,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Failed to save settings!"
            )
            dialog.run()
            dialog.destroy()
    
    def on_cancel(self, button):
        """Cancel and close without saving."""
        # Clean up PID file before closing
        try:
            with open(_PREFS_PIDFILE, "r") as f:
                cur = int(f.read().strip() or "0")
            if cur == os.getpid():
                os.remove(_PREFS_PIDFILE)
        except Exception:
            pass
        self.window.destroy()
        Gtk.main_quit()
    
    def on_ok(self, button):
        """Save, restart service, and close."""
        if self.save_config():
            # Restart the service
            service_restarted = self.restart_service()
            
            # Clean up PID file before closing
            try:
                with open(_PREFS_PIDFILE, "r") as f:
                    cur = int(f.read().strip() or "0")
                if cur == os.getpid():
                    os.remove(_PREFS_PIDFILE)
            except Exception:
                pass
            
            # Show final status if service restart failed
            if not service_restarted:
                dialog = Gtk.MessageDialog(
                    transient_for=self.window,
                    flags=0,
                    message_type=Gtk.MessageType.WARNING,
                    buttons=Gtk.ButtonsType.OK,
                    text="Settings saved, but service restart failed!"
                )
                dialog.format_secondary_text("You may need to manually restart the service.")
                dialog.run()
                dialog.destroy()
            
            self.window.destroy()
            Gtk.main_quit()
        else:
            self.on_apply(button)  # Show error dialog

    def on_record_clicked(self, button):
        """Handle microphone test recording."""
        if not hasattr(self, "recording") or not self.recording:
            self.start_recording()
        else:
            self.stop_recording()
    
    def start_recording(self):
        """Start microphone test recording."""
        try:
            import sounddevice as sd
            import numpy as np
            
            self.recording = True
            self.record_button.set_label("Stop Recording")
            
            # Start level monitoring
            self._start_level_monitoring()
            
            # Record for 3 seconds
            GLib.timeout_add(3000, self.stop_recording)
            
        except Exception as e:
            print(f"Recording error: {e}")
            self.recording = False
            self.record_button.set_label("Start Recording")
    
    def stop_recording(self):
        """Stop microphone test recording."""
        self.recording = False
        self.record_button.set_label("Start Recording")
        self._stop_level_monitoring()
        return False  # Remove timeout
    
    def _start_level_monitoring(self):
        """Start monitoring microphone levels."""
        try:
            import sounddevice as sd
            import numpy as np
            
            def audio_callback(indata, frames, time, status):
                if hasattr(self, "level_bar"):
                    level = np.sqrt(np.mean(indata**2))
                    GLib.idle_add(lambda: self.level_bar.set_value(min(level * 10, 1.0)))
            
            self.stream = sd.InputStream(callback=audio_callback)
            self.stream.start()
            
        except Exception as e:
            print(f"Level monitoring error: {e}")
    
    def _stop_level_monitoring(self):
        """Stop monitoring microphone levels."""
        if hasattr(self, "stream"):
            try:
                self.stream.stop()
                self.stream.close()
                delattr(self, "stream")
            except:
                pass
        if hasattr(self, "level_bar"):
            self.level_bar.set_value(0.0)

def main():
    _acquire_prefs_singleton()
    app = PreferencesWindow()
    Gtk.main()

if __name__ == "__main__":
    main()

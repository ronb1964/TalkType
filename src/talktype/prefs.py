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
        # Set GTK theme to prefer dark mode
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-application-prefer-dark-theme", True)
        
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
        self.ok_btn.grab_default()  # Now safe to grab default after window is shown
        self.window.present()  # Bring window to front
        self.window.set_keep_above(True)  # Force window on top temporarily
        GLib.timeout_add_seconds(1, self._remove_keep_above)  # Remove keep_above after 1 second
        
        # Initialize UI state after window is shown
        GLib.timeout_add(200, self._update_hotkey_ui_state)
        GLib.timeout_add(200, self._update_language_ui_state)
        # Don't auto-start level monitoring - only when user clicks record button
        
    def load_config(self):
        """Load config from TOML file."""
        defaults = {
            "model": "small",
            "device": "cuda", 
            "hotkey": "F8",
            "beeps": True,
            "smart_quotes": True,
            "mode": "hold",
            "toggle_hotkey": "F9",
            "mic": "",
            "notify": False,
            "language": "en",
            "language_mode": "manual",
            "auto_space": True,
            "auto_period": True,
            "paste_injection": False,
            "injection_mode": "type",
            "launch_at_login": False
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
        # Use cuda_helper for reliable detection
        try:
            from . import cuda_helper
            return cuda_helper.has_cuda_libraries()
        except ImportError:
            # Fallback to old method if cuda_helper not available
            try:
                from faster_whisper import WhisperModel
                print("🔍 Checking CUDA availability in preferences...")
                model = WhisperModel("tiny", device="cuda")
                del model
                print("✅ CUDA availability check passed!")
                return True
            except Exception as e:
                print(f"❌ CUDA availability check failed: {e}")
                return False
    
    def _refresh_device_options(self):
        """Refresh the device dropdown options based on current CUDA availability."""
        if not hasattr(self, 'device_combo'):
            return
            
        # Clear existing options except CPU
        self.device_combo.remove_all()
        self.device_combo.append("cpu", "CPU")
        
        # Check CUDA availability and add option if available
        cuda_available = self._check_cuda_availability()
        if cuda_available:
            self.device_combo.append("cuda", "CUDA (GPU)")
            tooltip_text = "Processing device for AI transcription:\n• CPU: works on all computers, slower\n• CUDA (GPU): much faster, requires NVIDIA graphics card"
        else:
            tooltip_text = "Processing device for AI transcription:\n• CPU: works on all computers\n• CUDA: not available (no NVIDIA GPU or missing CUDA libraries)"
            # If config has CUDA but it's not available, reset to CPU
            if self.config["device"] == "cuda":
                self.config["device"] = "cpu"
        
        # Set active selection and tooltip
        self.device_combo.set_active_id(self.config["device"])
        self.device_combo.set_tooltip_text(tooltip_text)
    
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
        
        self.ok_btn = Gtk.Button(label="OK")
        self.ok_btn.connect("clicked", self.on_ok)
        self.ok_btn.set_can_default(True)
        
        button_box.pack_start(cancel_btn, False, False, 0)
        button_box.pack_start(apply_btn, False, False, 0)
        button_box.pack_start(self.ok_btn, False, False, 0)
        
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
        self.model_combo = model_combo  # Store reference for later use
        model_combo.connect("changed", self._on_model_changed)
        model_combo.set_tooltip_text(
            "Whisper AI model size - choose based on your needs:\n\n"
            "• tiny (39 MB): Fastest, basic accuracy - quick notes\n"
            "• base (74 MB): Fast, good accuracy - casual use\n"
            "• small (244 MB): Balanced - recommended for most users\n"
            "• medium (769 MB): Slower, very accurate - professional use\n"
            "• large-v3 (~3 GB): Best accuracy - technical/professional work\n"
            "  ⚠️ Takes 30-60 seconds to load initially\n\n"
            "Larger models provide:\n"
            "• Better word recognition (technical terms, proper nouns)\n"
            "• Improved punctuation and context awareness\n"
            "• Better handling of accents and background noise"
        )
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
        
        # Store device combo for later refresh
        self.device_combo = device_combo
        
        # Populate device options
        self._refresh_device_options()
        
        device_combo.connect("changed", lambda x: self.update_config("device", x.get_active_id()))
        grid.attach(device_combo, 1, row, 1, 1)
        row += 1
        
        # Language Mode (first)
        grid.attach(Gtk.Label(label="Language Mode:", xalign=0), 0, row, 1, 1)
        self.lang_mode_combo = Gtk.ComboBoxText()
        self.lang_mode_combo.set_can_focus(True)
        self.lang_mode_combo.connect("button-press-event", self._on_combo_button_press)
        self.lang_mode_combo.append("auto", "Auto-detect")
        self.lang_mode_combo.append("manual", "Manual Selection (Faster)")
        self.lang_mode_combo.set_active_id(self.config.get("language_mode", "auto"))
        self.lang_mode_combo.connect("changed", lambda x: self.update_config("language_mode", x.get_active_id()))
        self.lang_mode_combo.connect("changed", self._on_language_mode_changed)
        self.lang_mode_combo.set_tooltip_text("Auto-detect: automatically detect language from speech\nManual Selection (Faster): select a specific language for faster processing")
        grid.attach(self.lang_mode_combo, 1, row, 1, 1)
        row += 1
        
        # Language Selection (second)
        self.lang_label = Gtk.Label(label="Language:", xalign=0)
        grid.attach(self.lang_label, 0, row, 1, 1)
        self.lang_combo = Gtk.ComboBoxText()
        self.lang_combo.set_can_focus(True)
        self.lang_combo.connect("button-press-event", self._on_combo_button_press)
        
        # Add language options with flags
        languages = [
            ("", "🌐 Auto-detect"),
            ("en", "🇺🇸 English"),
            ("es", "🇪🇸 Spanish"),
            ("fr", "🇫🇷 French"),
            ("de", "🇩🇪 German"),
            ("it", "🇮🇹 Italian"),
            ("pt", "🇵🇹 Portuguese"),
            ("ru", "🇷🇺 Russian"),
            ("ja", "🇯🇵 Japanese"),
            ("ko", "🇰🇷 Korean"),
            ("zh", "🇨🇳 Chinese"),
            ("ar", "🇸🇦 Arabic"),
            ("hi", "🇮🇳 Hindi"),
            ("nl", "🇳🇱 Dutch"),
            ("sv", "🇸🇪 Swedish"),
            ("no", "🇳🇴 Norwegian"),
            ("da", "🇩🇰 Danish"),
            ("fi", "🇫🇮 Finnish"),
            ("pl", "🇵🇱 Polish"),
            ("tr", "🇹🇷 Turkish"),
            ("he", "🇮🇱 Hebrew"),
            ("th", "🇹🇭 Thai"),
            ("vi", "🇻🇳 Vietnamese"),
            ("uk", "🇺🇦 Ukrainian"),
            ("cs", "🇨🇿 Czech"),
            ("hu", "🇭🇺 Hungarian"),
            ("ro", "🇷🇴 Romanian"),
            ("bg", "🇧🇬 Bulgarian"),
            ("hr", "🇭🇷 Croatian"),
            ("sk", "🇸🇰 Slovak"),
            ("sl", "🇸🇮 Slovenian"),
            ("et", "🇪🇪 Estonian"),
            ("lv", "🇱🇻 Latvian"),
            ("lt", "🇱🇹 Lithuanian")
        ]
        
        for code, name in languages:
            self.lang_combo.append(code, name)
        
        # Set current selection
        current_lang = self.config.get("language", "")
        self.lang_combo.set_active_id(current_lang)
        if self.lang_combo.get_active_id() is None:
            self.lang_combo.set_active_id("")  # Default to auto-detect
            
        self.lang_combo.connect("changed", lambda x: self.update_config("language", x.get_active_id()))
        self.lang_combo.set_tooltip_text("Select the language for speech recognition.\nOnly used when Language Mode is set to 'Manual'.")
        grid.attach(self.lang_combo, 1, row, 1, 1)
        row += 1
        
        # Initial visibility will be set by _update_language_ui_state
        
        # Mode selection
        grid.attach(Gtk.Label(label="Mode:", xalign=0), 0, row, 1, 1)
        self.mode_combo = Gtk.ComboBoxText()
        
        # Fix dropdown responsiveness - enable proper focus handling
        self.mode_combo.set_can_focus(True)
        # Add button press event to ensure dropdown opens reliably
        self.mode_combo.connect("button-press-event", self._on_combo_button_press)
        
        self.mode_combo.append("hold", "Hold to Talk")
        self.mode_combo.append("toggle", "Press to Toggle")
        self.mode_combo.set_active_id(self.config["mode"])
        self.mode_combo.connect("changed", lambda x: self.update_config("mode", x.get_active_id()))
        self.mode_combo.connect("changed", self._on_mode_changed)
        self.mode_combo.set_tooltip_text("How to activate dictation:\n• Hold to Talk: hold hotkey down while speaking\n• Press to Toggle: press once to start, press again to stop")
        grid.attach(self.mode_combo, 1, row, 1, 1)
        row += 1
        
        # Dynamic Hotkey (shows based on mode)
        self.hotkey_label = Gtk.Label(label="Hold Hotkey:", xalign=0)
        grid.attach(self.hotkey_label, 0, row, 1, 1)
        
        self.hotkey_combo = Gtk.ComboBoxText()
        
        # Fix dropdown responsiveness - enable proper focus handling
        self.hotkey_combo.set_can_focus(True)
        # Add button press event to ensure dropdown opens reliably
        self.hotkey_combo.connect("button-press-event", self._on_combo_button_press)
        
        # Add F-key options (most practical for dictation)
        hotkeys = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"]
        
        for key in hotkeys:
            self.hotkey_combo.append(key, key)
        
        # Set current selection or default to F8
        current_hotkey = self.config.get("hotkey", "F8")
        if current_hotkey in hotkeys:
            self.hotkey_combo.set_active_id(current_hotkey)
        else:
            self.hotkey_combo.set_active_id("F8")  # Default fallback
            
        self.hotkey_combo.connect("changed", lambda x: self.update_config("hotkey", x.get_active_id()))
        self.hotkey_combo.set_tooltip_text("Choose the key to hold down for dictation.\nRecommended: F8 (default), F6, F7, F9, F10\nAvoid: F1 (help), F5 (refresh), F11 (fullscreen), F12 (dev tools)")
        grid.attach(self.hotkey_combo, 1, row, 1, 1)
        row += 1
        
        # Toggle hotkey (initially hidden for hold mode)
        self.toggle_label = Gtk.Label(label="Toggle Hotkey:", xalign=0)
        self.toggle_combo = Gtk.ComboBoxText()
        
        # Fix dropdown responsiveness - enable proper focus handling
        self.toggle_combo.set_can_focus(True)
        # Add button press event to ensure dropdown opens reliably
        self.toggle_combo.connect("button-press-event", self._on_combo_button_press)
        
        # Add same options for toggle key
        for key in hotkeys:
            self.toggle_combo.append(key, key)
            
        # Set current selection or default to F9
        current_toggle = self.config.get("toggle_hotkey", "F9")
        if current_toggle in hotkeys:
            self.toggle_combo.set_active_id(current_toggle)
        else:
            self.toggle_combo.set_active_id("F9")  # Default fallback
            
        self.toggle_combo.connect("changed", lambda x: self.update_config("toggle_hotkey", x.get_active_id()))
        self.toggle_combo.set_tooltip_text("Choose the key for toggle mode (press once to start, press again to stop).\nRecommended: F9 (default), F10, F6, F7\nOnly used when Mode is set to 'Press to Toggle'.")
        
        # Attach toggle elements to grid
        grid.attach(self.toggle_label, 0, row, 1, 1)
        grid.attach(self.toggle_combo, 1, row, 1, 1)
        row += 1
        
        # Initial visibility will be set by _update_hotkey_ui_state
        
        # Add horizontal separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(20)
        separator.set_margin_bottom(10)
        grid.attach(separator, 0, row, 2, 1)
        row += 1
        
        # Launch at login checkbox
        self.launch_at_login_check = Gtk.CheckButton(label="Launch TalkType at login")
        self.launch_at_login_check.set_active(self.config.get("launch_at_login", False))
        self.launch_at_login_check.connect("toggled", lambda x: self.update_config("launch_at_login", x.get_active()))
        self.launch_at_login_check.set_tooltip_text("Automatically start TalkType when you log in to your desktop.\nUseful for having dictation always available.")
        grid.attach(self.launch_at_login_check, 0, row, 2, 1)
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
        
        # Advanced Microphone Test Section
        grid.attach(Gtk.Label(label="Microphone Test:", xalign=0), 0, row, 1, 1)
        
        # Create a vertical box for the microphone test controls
        mic_test_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        
        # Volume slider
        volume_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        volume_label = Gtk.Label(label="Input Volume:")
        self.volume_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        self.volume_scale.set_range(0, 100)
        self.volume_scale.set_value(self.get_system_mic_volume())  # Get current system volume
        self.volume_scale.set_hexpand(True)
        self.volume_scale.set_tooltip_text("Adjust system microphone input volume")
        self.volume_scale.connect("value-changed", self.on_volume_changed)
        volume_box.pack_start(volume_label, False, False, 0)
        volume_box.pack_start(self.volume_scale, True, True, 0)
        mic_test_box.pack_start(volume_box, False, False, 0)
        
        # Level meter
        level_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        level_label = Gtk.Label(label="Input Level:")
        self.level_bar = Gtk.LevelBar()
        self.level_bar.set_min_value(0.0)
        self.level_bar.set_max_value(1.0)
        self.level_bar.set_value(0.0)
        self.level_bar.set_hexpand(True)
        self.level_bar.set_tooltip_text("Real-time microphone input level")
        level_box.pack_start(level_label, False, False, 0)
        level_box.pack_start(self.level_bar, True, True, 0)
        mic_test_box.pack_start(level_box, False, False, 0)
        
        # Control buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.start_record_btn = Gtk.Button(label="🔴 Start Recording")
        self.stop_record_btn = Gtk.Button(label="⏹️ Stop Recording")
        self.replay_btn = Gtk.Button(label="▶️ Replay")
        
        self.start_record_btn.connect("clicked", self.on_start_recording)
        self.stop_record_btn.connect("clicked", self.on_stop_recording)
        self.replay_btn.connect("clicked", self.on_replay_recording)
        
        # Initial button states
        self.stop_record_btn.set_sensitive(False)
        self.replay_btn.set_sensitive(False)
        
        button_box.pack_start(self.start_record_btn, False, False, 0)
        button_box.pack_start(self.stop_record_btn, False, False, 0)
        button_box.pack_start(self.replay_btn, False, False, 0)
        mic_test_box.pack_start(button_box, False, False, 0)
        
        grid.attach(mic_test_box, 1, row, 1, 1)
        row += 1
        
        # Initialize microphone test state
        self.recording = False
        self.recorded_audio = None
        self.level_monitor_timer = None
        
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

        # Add horizontal separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(20)
        separator.set_margin_bottom(10)
        grid.attach(separator, 0, row, 2, 1)
        row += 1

        # Auto timeout checkbox
        self.auto_timeout_check = Gtk.CheckButton(label="Enable auto-timeout after inactivity")
        self.auto_timeout_check.set_active(self.config.get("auto_timeout_enabled", False))
        self.auto_timeout_check.connect("toggled", lambda x: self.update_config("auto_timeout_enabled", x.get_active()))
        self.auto_timeout_check.connect("toggled", self._on_auto_timeout_toggled)
        self.auto_timeout_check.set_tooltip_text("Automatically stop the dictation service after a period of inactivity.\nThis helps save battery life on laptops and reduces CPU usage.")
        grid.attach(self.auto_timeout_check, 0, row, 2, 1)
        row += 1

        # Timeout duration (only visible when timeout is enabled)
        self.timeout_label = Gtk.Label(label="Timeout after (minutes):", xalign=0)
        grid.attach(self.timeout_label, 0, row, 1, 1)

        self.timeout_spin = Gtk.SpinButton()
        self.timeout_spin.set_range(1, 60)  # 1 to 60 minutes
        self.timeout_spin.set_increments(1, 5)
        self.timeout_spin.set_value(self.config.get("auto_timeout_minutes", 5))
        self.timeout_spin.connect("value-changed", lambda x: self.update_config("auto_timeout_minutes", int(x.get_value())))
        self.timeout_spin.set_tooltip_text("Number of minutes of inactivity before automatically stopping dictation.\n• 1-5 minutes: Very aggressive (good for short sessions)\n• 5-15 minutes: Balanced (recommended for laptop use)\n• 15-30 minutes: Conservative (good for desktop use)")
        grid.attach(self.timeout_spin, 1, row, 1, 1)
        row += 1

        # Set initial visibility of timeout controls
        self._update_timeout_ui_state()

        # Add horizontal separator before GPU section
        separator2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator2.set_margin_top(20)
        separator2.set_margin_bottom(10)
        grid.attach(separator2, 0, row, 2, 1)
        row += 1

        # GPU Detection Section Header
        gpu_header = Gtk.Label()
        gpu_header.set_markup('<b>🎮 GPU Detection</b>')
        gpu_header.set_xalign(0)
        gpu_header.set_margin_bottom(5)
        grid.attach(gpu_header, 0, row, 2, 1)
        row += 1

        # GPU Status Label
        self.gpu_status_label = Gtk.Label(label="Checking...", xalign=0)
        self.gpu_status_label.set_margin_start(10)
        grid.attach(self.gpu_status_label, 0, row, 2, 1)
        row += 1

        # CUDA Status Label
        self.cuda_status_label = Gtk.Label(label="", xalign=0)
        self.cuda_status_label.set_margin_start(10)
        self.cuda_status_label.set_margin_bottom(10)
        grid.attach(self.cuda_status_label, 0, row, 2, 1)
        row += 1

        # Button box for GPU actions
        gpu_button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        gpu_button_box.set_margin_start(10)

        # Check GPU button
        self.check_gpu_button = Gtk.Button(label="🔍 Check for NVIDIA GPU")
        self.check_gpu_button.connect("clicked", self._on_check_gpu_clicked)
        self.check_gpu_button.set_tooltip_text("Check if an NVIDIA graphics card is present on your system")
        gpu_button_box.pack_start(self.check_gpu_button, False, False, 0)

        # Download CUDA button
        self.download_cuda_button = Gtk.Button(label="📦 Download CUDA Libraries")
        self.download_cuda_button.connect("clicked", self._on_download_cuda_clicked)
        self.download_cuda_button.set_tooltip_text("Download CUDA libraries for GPU acceleration (~1.7GB download, 1.2GB installed)")
        self.download_cuda_button.set_sensitive(False)
        gpu_button_box.pack_start(self.download_cuda_button, False, False, 0)

        grid.attach(gpu_button_box, 0, row, 2, 1)
        row += 1

        # Initial GPU check
        GLib.timeout_add(500, self._initial_gpu_check)

        return grid
    
    def update_config(self, key, value):
        """Update config value."""
        self.config[key] = value

        # Handle autostart desktop file creation/removal
        if key == "launch_at_login":
            self._handle_autostart(value)

    def _on_model_changed(self, combo):
        """Handle model selection change with warning for large models."""
        # Prevent recursive calls when reverting model selection
        if hasattr(self, '_updating_model') and self._updating_model:
            return

        new_model = combo.get_active_id()

        # Show warning dialog for large-v3 model
        if new_model == "large-v3" and self.config.get("model") != "large-v3":
            dialog = Gtk.MessageDialog(
                transient_for=self.window,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK_CANCEL,
                text="Large Model Selected"
            )
            dialog.format_secondary_text(
                "The large-v3 model is approximately 3 GB in size.\n\n"
                "⏱️  First-time load: 30-60 seconds\n"
                "⏱️  Subsequent loads: 10-20 seconds\n\n"
                "The application will not respond to your dictation hotkey "
                "until the model has fully loaded.\n\n"
                "Do you want to proceed with this model?"
            )

            response = dialog.run()
            dialog.destroy()

            if response == Gtk.ResponseType.CANCEL:
                # Revert to previous model selection (block recursive call)
                self._updating_model = True
                previous_model = self.config.get("model", "medium")
                combo.set_active_id(previous_model)
                self._updating_model = False
                return

        # Update config with new model
        self.update_config("model", new_model)

    def _handle_autostart(self, enable):
        """Create or remove autostart desktop file."""
        autostart_dir = os.path.expanduser("~/.config/autostart")
        desktop_file = os.path.join(autostart_dir, "talktype.desktop")
        
        if enable:
            # Create autostart directory if it doesn't exist
            os.makedirs(autostart_dir, exist_ok=True)
            
            # Get the path to the Poetry environment
            python_path = sys.executable
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            
            # Create desktop file content
            desktop_content = f"""[Desktop Entry]
Type=Application
Name=TalkType
GenericName=Voice Dictation
Comment=AI-powered dictation for Wayland using Faster-Whisper
Exec={python_path} -c "import sys; sys.path.insert(0, '{project_dir}'); from src.talktype.tray import main; main()"
Icon={project_dir}/AppDir/io.github.ronb1964.TalkType.svg
Terminal=false
Categories=Utility;
Keywords=dictation;voice;speech;whisper;ai;transcription;
StartupNotify=true
StartupWMClass=TalkType
X-GNOME-Autostart-enabled=true
"""
            
            try:
                with open(desktop_file, "w") as f:
                    f.write(desktop_content)
                print(f"✅ Created autostart file: {desktop_file}")
            except Exception as e:
                print(f"❌ Failed to create autostart file: {e}")
        else:
            # Remove autostart file
            try:
                if os.path.exists(desktop_file):
                    os.remove(desktop_file)
                    print(f"✅ Removed autostart file: {desktop_file}")
            except Exception as e:
                print(f"❌ Failed to remove autostart file: {e}")
    
    def _on_combo_button_press(self, widget, event):
        """Handle button press events on combo boxes to ensure they open reliably."""
        # Ensure the widget has focus before processing the click
        if not widget.has_focus():
            widget.grab_focus()
        # Let GTK handle the normal click event
        return False
    
    def get_selected_device_idx(self):
        """Get the device index for the currently selected microphone."""
        current_mic = self.config.get("mic", "")
        if not current_mic:
            return None
            
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            for i, device in enumerate(devices):
                if device.get("max_input_channels", 0) > 0 and current_mic in device.get("name", ""):
                    return i
        except Exception:
            pass
        return None
    
    def start_level_monitoring(self):
        """Start monitoring microphone input levels."""
        try:
            import sounddevice as sd
            import numpy as np
            
            device_idx = self.get_selected_device_idx()
            
            def audio_callback(indata, frames, time, status):
                if self.recording or self.level_monitor_timer:
                    # Calculate RMS level
                    rms = np.sqrt(np.mean(indata**2))
                    # Update level bar on main thread
                    GLib.idle_add(self.update_level_bar, min(rms * 10, 1.0))
            
            # Start input stream for level monitoring
            self.level_stream = sd.InputStream(
                callback=audio_callback,
                channels=1,
                samplerate=16000,
                device=device_idx,
                blocksize=1024
            )
            self.level_stream.start()
            
        except Exception as e:
            print(f"Failed to start level monitoring: {e}")
    
    def stop_level_monitoring(self):
        """Stop monitoring microphone input levels."""
        try:
            if hasattr(self, 'level_stream'):
                self.level_stream.stop()
                self.level_stream.close()
                delattr(self, 'level_stream')
            self.level_bar.set_value(0.0)
        except Exception:
            pass
    
    def update_level_bar(self, level):
        """Update the level bar with current audio level."""
        self.level_bar.set_value(level)
        return False  # Don't repeat
    
    def on_start_recording(self, button):
        """Start recording microphone input."""
        try:
            import sounddevice as sd
            import numpy as np
            
            device_idx = self.get_selected_device_idx()
            
            # Start recording
            self.recording = True
            self.recorded_frames = []
            
            def audio_callback(indata, frames, time, status):
                if self.recording:
                    self.recorded_frames.append(indata.copy())
                    # Update level bar
                    rms = np.sqrt(np.mean(indata**2))
                    GLib.idle_add(self.update_level_bar, min(rms * 10, 1.0))
            
            self.record_stream = sd.InputStream(
                callback=audio_callback,
                channels=1,
                samplerate=16000,
                device=device_idx,
                dtype='float32'
            )
            self.record_stream.start()
            
            # Update button states
            self.start_record_btn.set_sensitive(False)
            self.stop_record_btn.set_sensitive(True)
            self.replay_btn.set_sensitive(False)
            
        except Exception as e:
            self.show_error_dialog("Recording failed!", str(e))
    
    def on_stop_recording(self, button):
        """Stop recording microphone input."""
        try:
            self.recording = False
            
            if hasattr(self, 'record_stream'):
                self.record_stream.stop()
                self.record_stream.close()
            
            # Combine recorded frames
            if self.recorded_frames:
                import numpy as np
                self.recorded_audio = np.concatenate(self.recorded_frames, axis=0)
            
            # Update button states
            self.start_record_btn.set_sensitive(True)
            self.stop_record_btn.set_sensitive(False)
            self.replay_btn.set_sensitive(len(self.recorded_frames) > 0)
            
            # Reset level bar
            self.level_bar.set_value(0.0)
            
        except Exception as e:
            self.show_error_dialog("Stop recording failed!", str(e))
    
    def on_replay_recording(self, button):
        """Replay the recorded audio."""
        try:
            if self.recorded_audio is not None:
                import sounddevice as sd
                # Amplify the audio for better playback volume (3x boost)
                import numpy as np
                amplified_audio = self.recorded_audio * 3.0
                # Ensure we don't clip (values stay between -1 and 1)
                amplified_audio = np.clip(amplified_audio, -1.0, 1.0)
                sd.play(amplified_audio, samplerate=16000)
            
        except Exception as e:
            self.show_error_dialog("Playback failed!", str(e))
    
    def show_error_dialog(self, title, message):
        """Show an error dialog."""
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=title
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()
    
    def get_system_mic_volume(self):
        """Get the current system microphone volume."""
        try:
            import subprocess
            # Try to get microphone volume using pactl (PulseAudio)
            result = subprocess.run(
                ["pactl", "get-source-volume", "@DEFAULT_SOURCE@"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                # Parse volume from output like "Volume: mono: 43423 /  66% / -10.73 dB"
                for line in result.stdout.split('\n'):
                    if 'Volume:' in line and '%' in line:
                        # Extract percentage - look for pattern "/ XX% /"
                        if '/' in line and '%' in line:
                            parts = line.split('/')
                            for part in parts:
                                part = part.strip()
                                if part.endswith('%'):
                                    try:
                                        return int(part[:-1])
                                    except ValueError:
                                        continue
        except FileNotFoundError:
            # pactl not installed - silently use fallback (common on non-PulseAudio systems)
            pass
        except Exception as e:
            print(f"Failed to get system mic volume: {e}")

        # Fallback to 50% if we can't get the actual volume
        return 50
    
    def set_system_mic_volume(self, volume_percent):
        """Set the system microphone volume."""
        try:
            import subprocess
            # Set microphone volume using pactl (PulseAudio)
            subprocess.run(
                ["pactl", "set-source-volume", "@DEFAULT_SOURCE@", f"{volume_percent}%"],
                capture_output=True, timeout=2
            )
        except FileNotFoundError:
            # pactl not installed - silently skip (common on non-PulseAudio systems)
            pass
        except Exception as e:
            print(f"Failed to set system mic volume: {e}")
    
    def on_volume_changed(self, scale):
        """Handle volume slider changes."""
        volume = int(scale.get_value())
        self.set_system_mic_volume(volume)
    
    def _on_mode_changed(self, widget):
        """Handle mode change to show/hide appropriate hotkey fields."""
        mode = widget.get_active_id()
        if mode == "hold":
            # Show hold hotkey, hide toggle hotkey
            self.hotkey_label.set_visible(True)
            self.hotkey_combo.set_visible(True)
            self.toggle_label.set_visible(False)
            self.toggle_combo.set_visible(False)
        else:  # toggle mode
            # Show toggle hotkey, hide hold hotkey
            self.hotkey_label.set_visible(False)
            self.hotkey_combo.set_visible(False)
            self.toggle_label.set_visible(True)
            self.toggle_combo.set_visible(True)
    
    def _on_language_mode_changed(self, widget):
        """Handle language mode change to show/hide language selection."""
        mode = widget.get_active_id()
        if mode == "auto":
            # Hide language selection
            self.lang_label.set_visible(False)
            self.lang_combo.set_visible(False)
        else:  # manual mode
            # Show language selection
            self.lang_label.set_visible(True)
            self.lang_combo.set_visible(True)
    
    def _update_hotkey_ui_state(self):
        """Update hotkey UI state based on current config."""
        mode = self.config.get("mode", "hold")
        if mode == "hold":
            # Show hold hotkey, hide toggle hotkey
            self.hotkey_label.set_visible(True)
            self.hotkey_combo.set_visible(True)
            self.toggle_label.set_visible(False)
            self.toggle_combo.set_visible(False)
        else:  # toggle mode
            # Show toggle hotkey, hide hold hotkey
            self.hotkey_label.set_visible(False)
            self.hotkey_combo.set_visible(False)
            self.toggle_label.set_visible(True)
            self.toggle_combo.set_visible(True)
        return False  # Don't repeat
    
    def _update_language_ui_state(self):
        """Update language UI state based on current config."""
        language_mode = self.config.get("language_mode", "auto")
        if language_mode == "auto":
            # Hide language selection when auto-detect is selected
            self.lang_label.set_visible(False)
            self.lang_combo.set_visible(False)
        else:  # manual mode
            # Show language selection when manual is selected
            self.lang_label.set_visible(True)
            self.lang_combo.set_visible(True)

    def _on_auto_timeout_toggled(self, checkbox):
        """Handle auto-timeout checkbox toggle."""
        self._update_timeout_ui_state()

    def _update_timeout_ui_state(self):
        """Update timeout UI visibility based on checkbox state."""
        if hasattr(self, 'timeout_label'):
            is_enabled = self.config.get("auto_timeout_enabled", False)
            self.timeout_label.set_visible(is_enabled)
            self.timeout_spin.set_visible(is_enabled)
        return False  # Don't repeat

    def _initial_gpu_check(self):
        """Perform initial GPU check when preferences window opens."""
        self._check_gpu_status()
        return False  # Don't repeat

    def _check_gpu_status(self):
        """Check GPU and CUDA status and update UI."""
        try:
            # Import cuda_helper
            try:
                from . import cuda_helper
            except ImportError:
                # If cuda_helper doesn't exist, create stub
                self.gpu_status_label.set_text("GPU detection not available in this build")
                self.cuda_status_label.set_text("")
                self.check_gpu_button.set_sensitive(False)
                self.download_cuda_button.set_sensitive(False)
                return
            
            # Check for NVIDIA GPU
            has_gpu = cuda_helper.detect_nvidia_gpu()
            has_cuda = cuda_helper.has_cuda_libraries()
            
            if has_gpu:
                gpu_name = cuda_helper.detect_nvidia_gpu()
                if isinstance(gpu_name, str) and len(gpu_name) > 5:
                    self.gpu_status_label.set_markup(f'<span color="#4CAF50">✓ NVIDIA GPU detected: {gpu_name}</span>')
                else:
                    self.gpu_status_label.set_markup('<span color="#4CAF50">✓ NVIDIA GPU detected</span>')
                
                if has_cuda:
                    self.cuda_status_label.set_markup('<span color="#4CAF50">✓ CUDA libraries installed</span>')
                    self.download_cuda_button.set_label("✓ CUDA Installed")
                    self.download_cuda_button.set_sensitive(False)
                else:
                    self.cuda_status_label.set_markup('<span color="#FF9800">⚠ CUDA libraries not installed (using CPU mode)</span>')
                    self.download_cuda_button.set_sensitive(True)
            else:
                self.gpu_status_label.set_markup('<span color="#9E9E9E">⊘ No NVIDIA GPU detected</span>')
                self.cuda_status_label.set_text("CPU mode only")
                self.download_cuda_button.set_sensitive(False)
                
        except Exception as e:
            self.gpu_status_label.set_text(f"Error checking GPU: {e}")
            self.cuda_status_label.set_text("")
            print(f"GPU check error: {e}")

    def _on_check_gpu_clicked(self, button):
        """Handle Check GPU button click."""
        button.set_label("🔄 Checking...")
        button.set_sensitive(False)
        
        def check_and_update():
            self._check_gpu_status()
            button.set_label("🔍 Check for NVIDIA GPU")
            button.set_sensitive(True)
            return False
        
        GLib.timeout_add(100, check_and_update)

    def _on_download_cuda_clicked(self, button):
        """Handle Download CUDA button click."""
        try:
            from . import cuda_helper
        except ImportError:
            return
        
        # Show confirmation dialog
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Download CUDA Libraries?"
        )
        dialog.format_secondary_text(
            "This will download approximately 1.7GB of CUDA libraries "
            "(1.2GB installed) to enable GPU acceleration.\n\n"
            "Libraries will be stored in ~/.local/share/TalkType/cuda\n\n"
            "This may take several minutes depending on your connection.\n\n"
            "Continue?"
        )
        
        response = dialog.run()
        dialog.destroy()
        
        if response == Gtk.ResponseType.YES:
            # Create progress dialog with progress bar
            progress_dialog = Gtk.Dialog(
                title="Downloading CUDA Libraries",
                transient_for=self.window,
                flags=0
            )
            progress_dialog.set_default_size(400, 150)
            
            content = progress_dialog.get_content_area()
            content.set_margin_top(20)
            content.set_margin_bottom(20)
            content.set_margin_start(20)
            content.set_margin_end(20)
            
            # Status label
            status_label = Gtk.Label(label="Preparing download...")
            status_label.set_margin_bottom(10)
            content.pack_start(status_label, False, False, 0)
            
            # Progress bar
            progress_bar = Gtk.ProgressBar()
            progress_bar.set_show_text(True)
            progress_bar.set_margin_bottom(10)
            content.pack_start(progress_bar, False, False, 0)
            
            progress_dialog.show_all()
            
            button.set_sensitive(False)
            
            import threading
            
            def progress_callback(message, percent):
                """Update progress dialog from download thread."""
                def update_ui():
                    status_label.set_text(message)
                    progress_bar.set_fraction(percent / 100.0)
                    progress_bar.set_text(f"{percent}%")
                    return False
                GLib.idle_add(update_ui)
            
            def download_thread():
                """Run download in background thread."""
                success = cuda_helper.download_cuda_libraries(progress_callback)
                
                def finish_download():
                    progress_dialog.destroy()

                    if success:
                        # Auto-enable GPU mode in config after successful download
                        if self.s.device != "cuda":
                            self.s.device = "cuda"
                            self.save_settings()
                            # Update device combo to reflect change
                            if hasattr(self, 'device_combo'):
                                self.device_combo.set_active_id("cuda")

                        # Refresh GPU status
                        self._check_gpu_status()

                        # Refresh device dropdown to show CUDA option
                        self._refresh_device_options()

                        # Show success dialog
                        success_dialog = Gtk.MessageDialog(
                            transient_for=self.window,
                            flags=0,
                            message_type=Gtk.MessageType.INFO,
                            buttons=Gtk.ButtonsType.OK,
                            text="CUDA Libraries Installed!"
                        )
                        success_dialog.format_secondary_text(
                            "GPU acceleration is now enabled and ready to use.\n\n"
                            "The app will now use GPU for faster transcription."
                        )
                        success_dialog.run()
                        success_dialog.destroy()
                    else:
                        button.set_sensitive(True)
                        # Show error dialog
                        error_dialog = Gtk.MessageDialog(
                            transient_for=self.window,
                            flags=0,
                            message_type=Gtk.MessageType.ERROR,
                            buttons=Gtk.ButtonsType.OK,
                            text="Download Failed"
                        )
                        error_dialog.format_secondary_text(
                            "Failed to download CUDA libraries.\n\n"
                            "Please check your internet connection and try again."
                        )
                        error_dialog.run()
                        error_dialog.destroy()
                    
                    return False
                
                GLib.idle_add(finish_download)
            
            # Start download in background thread
            thread = threading.Thread(target=download_thread, daemon=True)
            thread.start()
    
    def _start_level_monitoring(self):
        """Initialize level monitoring after window is shown."""
        self.start_level_monitoring()
        return False  # Don't repeat
    
    def on_window_close(self, widget, event):
        """Handle window close event to clean up PID file."""
        # Stop level monitoring
        self.stop_level_monitoring()
        
        # Stop any active recording
        if hasattr(self, 'recording') and self.recording:
            self.recording = False
            if hasattr(self, 'record_stream'):
                try:
                    self.record_stream.stop()
                    self.record_stream.close()
                except Exception:
                    pass
        
        # Clean up PID file
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
            # Kill existing talktype.app processes
            subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
            # Wait a moment for processes to terminate
            import time
            time.sleep(1)
            # Start the service again
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            subprocess.Popen([sys.executable, "-m", "src.talktype.app"], 
                           cwd=project_dir, 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"Failed to restart service: {e}")
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

def main():
    _acquire_prefs_singleton()
    app = PreferencesWindow()
    Gtk.main()

if __name__ == "__main__":
    main()

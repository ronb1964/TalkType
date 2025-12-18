import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib
import os
import subprocess
import sys
import atexit
import dbus
from .config import CONFIG_PATH, load_custom_commands, save_custom_commands

# D-Bus interface for communicating with the TalkType service
DBUS_SERVICE = "io.github.ronb1964.TalkType"
DBUS_OBJECT = "/io/github/ronb1964/TalkType"
DBUS_INTERFACE = "io.github.ronb1964.TalkType"

def _get_dbus_interface():
    """Get the D-Bus interface for TalkType service, or None if not available."""
    try:
        bus = dbus.SessionBus()
        proxy = bus.get_object(DBUS_SERVICE, DBUS_OBJECT)
        return dbus.Interface(proxy, DBUS_INTERFACE)
    except Exception:
        return None


def apply_dark_dialog_style(dialog):
    """Apply consistent dark styling to dialogs to match other windows."""
    # Set dark theme preference
    settings = Gtk.Settings.get_default()
    if settings:
        settings.set_property("gtk-application-prefer-dark-theme", True)

    # Apply custom CSS for darker background (matching welcome screen)
    css_provider = Gtk.CssProvider()
    css_provider.load_from_data(b"""
        dialog {
            background-color: #2b2b2b;
        }
        dialog box {
            background-color: #2b2b2b;
        }
        dialog label {
            color: #ffffff;
        }
    """)

    style_context = dialog.get_style_context()
    style_context.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

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

        # Create window FIRST
        self.window = Gtk.Window(title="TalkType Preferences")
        self.window.set_name("preferences_window")  # Give window a name for CSS targeting
        self.window.set_default_size(500, 600)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.set_resizable(True)  # Allow resizing for smaller screens

        # Load custom CSS styling (after window is created)
        self._load_css()

        # Set window type hint to NORMAL to ensure proper window stacking
        # This prevents the "Tried to map a popup with a non-top most parent" error
        self.window.set_type_hint(Gdk.WindowTypeHint.NORMAL)

        # Load current config
        self.config = self.load_config()

        # Initialize model tracking to prevent repeated warnings
        self._last_selected_model = self.config.get("model")

        # Create UI
        self.create_ui()
        
        # Connect window close event to cleanup
        self.window.connect("delete-event", self.on_window_close)
        
        # Show window - force it to appear
        self.window.show_all()
        self.ok_btn.grab_default()  # Now safe to grab default after window is shown
        self.window.present()  # Bring window to front
        # Note: Don't use set_keep_above - it interferes with combo box popups

        # Initialize UI state after window is shown
        GLib.timeout_add(200, self._update_hotkey_ui_state)
        GLib.timeout_add(200, self._update_language_ui_state)
        # Don't auto-start level monitoring - only when user clicks record button

    def _load_css(self):
        """Load custom CSS stylesheet for preferences window ONLY (not globally)."""
        try:
            css_provider = Gtk.CssProvider()
            css_file = os.path.join(os.path.dirname(__file__), 'prefs_style.css')

            if os.path.exists(css_file):
                css_provider.load_from_path(css_file)
                # Apply CSS ONLY to preferences window, not the entire screen
                # This prevents style conflicts with dialogs (help, etc.)
                style_context = self.window.get_style_context()
                style_context.add_provider(
                    css_provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
                print("✅ Loaded custom CSS styling (prefs window only)")
            else:
                print(f"⚠️  CSS file not found: {css_file}")
        except Exception as e:
            print(f"❌ Failed to load CSS: {e}")

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
            "language": "",
            "language_mode": "auto",
            "auto_space": True,
            "auto_period": True,
            "paste_injection": False,
            "injection_mode": "auto",
            "launch_at_login": False,
            "auto_timeout_enabled": True,
            "auto_timeout_minutes": 5,
            "auto_check_updates": True
        }
        
        if os.path.exists(CONFIG_PATH):
            try:
                config = load_toml(CONFIG_PATH)
                defaults.update(config)
            except Exception as e:
                print(f"Error loading config: {e}")
        
        return defaults

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
                f.flush()  # Ensure file is written to disk
                os.fsync(f.fileno())  # Force write to disk
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def create_ui(self):
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Scrolled window for main content (allows scrolling on small screens)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(300)  # Minimum before scrolling kicks in

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
        self.notebook = Gtk.Notebook()
        self.main_scrolled = scrolled  # Store reference for scroll-to-top on tab switch
        notebook = self.notebook  # Local alias for compatibility

        # Connect to tab switch signal to scroll to top
        notebook.connect("switch-page", self.on_tab_switched)

        # General tab
        general_tab = self.create_general_tab()
        notebook.append_page(general_tab, Gtk.Label(label="General"))

        # Audio tab
        audio_tab = self.create_audio_tab()
        notebook.append_page(audio_tab, Gtk.Label(label="Audio"))

        # Advanced tab
        advanced_tab = self.create_advanced_tab()
        notebook.append_page(advanced_tab, Gtk.Label(label="Advanced"))

        # Commands tab (custom voice commands)
        commands_tab = self.create_commands_tab()
        notebook.append_page(commands_tab, Gtk.Label(label="Commands"))

        # Updates tab
        updates_tab = self.create_updates_tab()
        notebook.append_page(updates_tab, Gtk.Label(label="Updates"))

        vbox.pack_start(notebook, True, True, 0)

        # Version footer
        from . import __version__
        version_label = Gtk.Label()
        version_label.set_markup(f'<span size="small" color="#888888">TalkType v{__version__}</span>')
        version_label.set_halign(Gtk.Align.END)
        version_label.set_margin_top(5)
        version_label.set_margin_end(5)
        vbox.pack_start(version_label, False, False, 0)

        # Add content to scrolled window
        scrolled.add(vbox)
        main_vbox.pack_start(scrolled, True, True, 0)

        # Buttons (outside scrolled area so always visible)
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_margin_start(20)
        button_box.set_margin_end(20)
        button_box.set_margin_top(10)
        button_box.set_margin_bottom(15)

        # Help button on the left
        help_btn = Gtk.Button(label="❓ Help")
        help_btn.connect("clicked", self.on_help)
        help_btn.set_tooltip_text("Open TalkType help documentation")
        button_box.pack_start(help_btn, False, False, 0)

        # Add spacing to push other buttons to the right
        button_box.pack_start(Gtk.Label(), True, True, 0)

        # Standard buttons on the right
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

        main_vbox.pack_start(button_box, False, False, 0)
        self.window.add(main_vbox)
    
    def create_general_tab(self):
        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(10)
        grid.set_margin_start(20)
        grid.set_margin_end(20)
        grid.set_margin_top(20)
        grid.set_margin_bottom(20)

        row = 0

        # ===== AI MODEL SECTION =====
        model_header = Gtk.Label()
        model_header.set_markup('<b>AI Model Configuration</b>')
        model_header.set_xalign(0)
        model_header.set_margin_bottom(10)
        grid.attach(model_header, 0, row, 2, 1)
        row += 1

        # Model selection
        model_label = Gtk.Label(label="Model 💡:", xalign=0)
        model_label.set_tooltip_text(
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
        grid.attach(model_label, 0, row, 1, 1)
        model_combo = Gtk.ComboBoxText()
        model_combo.set_can_focus(True)
        model_combo.connect("button-press-event", self._on_combo_button_press)

        models = ["tiny", "base", "small", "medium", "large-v3"]
        for model in models:
            model_combo.append(model, model)  # append(id, text) - use model name as both ID and text
        model_combo.set_active_id(self.config["model"])
        self.model_combo = model_combo  # Store reference for later use
        model_combo.connect("changed", self._on_model_changed)
        # TESTING: Tooltip disabled to check if it interferes with dropdown popup
        # model_combo.set_tooltip_text(
        #     "Whisper AI model size - choose based on your needs:\n\n"
        #     "• tiny (39 MB): Fastest, basic accuracy - quick notes\n"
        #     "• base (74 MB): Fast, good accuracy - casual use\n"
        #     "• small (244 MB): Balanced - recommended for most users\n"
        #     "• medium (769 MB): Slower, very accurate - professional use\n"
        #     "• large-v3 (~3 GB): Best accuracy - technical/professional work\n"
        #     "  ⚠️ Takes 30-60 seconds to load initially\n\n"
        #     "Larger models provide:\n"
        #     "• Better word recognition (technical terms, proper nouns)\n"
        #     "• Improved punctuation and context awareness\n"
        #     "• Better handling of accents and background noise"
        # )
        grid.attach(model_combo, 1, row, 1, 1)
        row += 1
        
        # Device selection
        grid.attach(Gtk.Label(label="Device:", xalign=0), 0, row, 1, 1)
        device_combo = Gtk.ComboBoxText()
        device_combo.set_can_focus(True)
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
        lang_mode_label = Gtk.Label(label="Language Mode 💡:", xalign=0)
        lang_mode_label.set_tooltip_text("Auto-detect: automatically detect language from speech\nManual Selection (Faster): select a specific language for faster processing")
        grid.attach(lang_mode_label, 0, row, 1, 1)
        self.lang_mode_combo = Gtk.ComboBoxText()
        self.lang_mode_combo.set_can_focus(True)
        self.lang_mode_combo.connect("button-press-event", self._on_combo_button_press)
        self.lang_mode_combo.append("auto", "Auto-detect")
        self.lang_mode_combo.append("manual", "Manual Selection (Faster)")
        self.lang_mode_combo.set_active_id(self.config.get("language_mode", "auto"))
        self.lang_mode_combo.connect("changed", lambda x: self.update_config("language_mode", x.get_active_id()))
        self.lang_mode_combo.connect("changed", self._on_language_mode_changed)
        grid.attach(self.lang_mode_combo, 1, row, 1, 1)
        row += 1
        
        # Language Selection (second)
        self.lang_label = Gtk.Label(label="Language 💡:", xalign=0)
        self.lang_label.set_tooltip_text("Select the language for speech recognition.\nOnly used when Language Mode is set to 'Manual'.")
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
        # Tooltip moved to label to avoid interference with dropdown popup
        grid.attach(self.lang_combo, 1, row, 1, 1)
        row += 1

        # Initial visibility will be set by _update_language_ui_state

        # ===== HOTKEY CONFIGURATION SECTION =====
        separator1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator1.set_margin_top(20)
        separator1.set_margin_bottom(15)
        grid.attach(separator1, 0, row, 2, 1)
        row += 1

        hotkey_header = Gtk.Label()
        hotkey_header.set_markup('<b>Hotkey Configuration</b>')
        hotkey_header.set_xalign(0)
        hotkey_header.set_margin_bottom(10)
        grid.attach(hotkey_header, 0, row, 2, 1)
        row += 1

        # Mode selection
        mode_label = Gtk.Label(label="Mode 💡:", xalign=0)
        mode_label.set_tooltip_text("How to activate dictation:\n• Hold to Talk: hold hotkey down while speaking\n• Press to Toggle: press once to start, press again to stop")
        grid.attach(mode_label, 0, row, 1, 1)
        self.mode_combo = Gtk.ComboBoxText()
        self.mode_combo.set_can_focus(True)
        self.mode_combo.connect("button-press-event", self._on_combo_button_press)

        self.mode_combo.append("hold", "Hold to Talk")
        self.mode_combo.append("toggle", "Press to Toggle")
        self.mode_combo.set_active_id(self.config["mode"])
        self.mode_combo.connect("changed", lambda x: self.update_config("mode", x.get_active_id()))
        self.mode_combo.connect("changed", self._on_mode_changed)
        grid.attach(self.mode_combo, 1, row, 1, 1)
        row += 1
        
        # Dynamic Hotkey (shows based on mode)
        self.hotkey_label = Gtk.Label(label="Hold Hotkey 💡:", xalign=0)
        self.hotkey_label.set_tooltip_text("Choose the key to hold down for dictation.\nRecommended: F8 (default), F6, F7, F9, F10\nAvoid: F1 (help), F5 (refresh), F11 (fullscreen), F12 (dev tools)")
        grid.attach(self.hotkey_label, 0, row, 1, 1)

        self.hotkey_combo = Gtk.ComboBoxText()
        self.hotkey_combo.set_can_focus(True)
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
        # Tooltip moved to label to avoid interference with dropdown popup
        grid.attach(self.hotkey_combo, 1, row, 1, 1)
        row += 1
        
        # Toggle hotkey (initially hidden for hold mode)
        self.toggle_label = Gtk.Label(label="Toggle Hotkey 💡:", xalign=0)
        self.toggle_label.set_tooltip_text("Choose the key for toggle mode (press once to start, press again to stop).\nRecommended: F9 (default), F10, F6, F7\nOnly used when Mode is set to 'Press to Toggle'.")
        self.toggle_combo = Gtk.ComboBoxText()
        self.toggle_combo.set_can_focus(True)
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
        # Tooltip moved to label to avoid interference with dropdown popup

        # Attach toggle elements to grid
        grid.attach(self.toggle_label, 0, row, 1, 1)
        grid.attach(self.toggle_combo, 1, row, 1, 1)
        row += 1

        # Test Hotkeys button
        test_hotkeys_btn = Gtk.Button(label="🎹 Test Hotkeys")
        test_hotkeys_btn.connect("clicked", self._on_test_hotkeys)
        test_hotkeys_btn.set_tooltip_text("Test your configured hotkeys to make sure they work")
        test_hotkeys_btn.set_halign(Gtk.Align.START)
        test_hotkeys_btn.set_margin_top(10)
        grid.attach(test_hotkeys_btn, 0, row, 2, 1)
        row += 1

        # Initial visibility will be set by _update_hotkey_ui_state

        # ===== STARTUP OPTIONS SECTION =====
        separator2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator2.set_margin_top(20)
        separator2.set_margin_bottom(15)
        grid.attach(separator2, 0, row, 2, 1)
        row += 1

        startup_header = Gtk.Label()
        startup_header.set_markup('<b>Startup Options</b>')
        startup_header.set_xalign(0)
        startup_header.set_margin_bottom(10)
        grid.attach(startup_header, 0, row, 2, 1)
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

        # ===== MICROPHONE SETUP SECTION =====
        mic_header = Gtk.Label()
        mic_header.set_markup('<b>Microphone Setup</b>')
        mic_header.set_xalign(0)
        mic_header.set_margin_bottom(10)
        grid.attach(mic_header, 0, row, 2, 1)
        row += 1

        # Microphone
        grid.attach(Gtk.Label(label="Microphone:", xalign=0), 0, row, 1, 1)
        mic_combo = Gtk.ComboBoxText()
        mic_combo.set_can_focus(True)
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
        self.volume_scale.set_tooltip_text("Adjust system microphone input volume (PipeWire/PulseAudio)")
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

        # ===== AUDIO FEEDBACK SECTION =====
        separator1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator1.set_margin_top(20)
        separator1.set_margin_bottom(15)
        grid.attach(separator1, 0, row, 2, 1)
        row += 1

        feedback_header = Gtk.Label()
        feedback_header.set_markup('<b>Audio &amp; Visual Feedback</b>')
        feedback_header.set_xalign(0)
        feedback_header.set_margin_bottom(10)
        grid.attach(feedback_header, 0, row, 2, 1)
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

        # Recording indicator
        indicator_check = Gtk.CheckButton(label="Show visual recording indicator")
        indicator_check.set_active(self.config.get("recording_indicator", True))
        indicator_check.connect("toggled", lambda x: self.update_config("recording_indicator", x.get_active()))
        indicator_check.set_tooltip_text("Show an animated visual indicator while recording.\nHelps you see that dictation is active and responding to your voice.")
        grid.attach(indicator_check, 0, row, 2, 1)
        row += 1

        # Indicator size
        size_label = Gtk.Label(label="  Indicator size 💡:", xalign=0)
        size_label.set_tooltip_text("Choose the size of the recording indicator.\nMedium is the default size.")
        grid.attach(size_label, 0, row, 1, 1)

        size_combo = Gtk.ComboBoxText()
        size_combo.connect("button-press-event", self._on_combo_button_press)
        size_combo.append("small", "Small (60%)")
        size_combo.append("medium", "Medium (100%)")
        size_combo.append("large", "Large (140%)")

        current_size = self.config.get("indicator_size", "medium")
        size_combo.set_active_id(current_size)
        size_combo.connect("changed", lambda x: self.update_config("indicator_size", x.get_active_id()))
        # Tooltip moved to label to avoid interference with dropdown popup
        grid.attach(size_combo, 1, row, 1, 1)
        row += 1

        # Indicator position
        pos_label = Gtk.Label(label="  Indicator position:", xalign=0)
        grid.attach(pos_label, 0, row, 1, 1)

        # Check if running on Wayland
        import os
        is_wayland = os.environ.get('WAYLAND_DISPLAY') or os.environ.get('XDG_SESSION_TYPE') == 'wayland'

        # Check if GNOME extension is available (enables positioning on Wayland)
        has_extension = False
        if is_wayland:
            try:
                from . import extension_helper
                ext_status = extension_helper.get_extension_status()
                has_extension = ext_status.get('installed', False) and ext_status.get('enabled', False)
            except:
                pass

        positions = [
            ("center", "Center"),
            ("top-left", "Top Left"),
            ("top-center", "Top Center"),
            ("top-right", "Top Right"),
            ("bottom-left", "Bottom Left"),
            ("bottom-center", "Bottom Center"),
            ("bottom-right", "Bottom Right"),
            ("left-center", "Left Center"),
            ("right-center", "Right Center")
        ]

        position_combo = Gtk.ComboBoxText()
        position_combo.connect("button-press-event", self._on_combo_button_press)
        for pos_id, pos_label_text in positions:
            position_combo.append(pos_id, pos_label_text)

        current_position = self.config.get("indicator_position", "center")
        position_combo.set_active_id(current_position)
        position_combo.connect("changed", lambda x: self.update_config("indicator_position", x.get_active_id()))

        # Enable positioning if: X11 session OR (Wayland + GNOME extension installed)
        if is_wayland and not has_extension:
            position_combo.set_tooltip_text("Note: On Wayland, window positioning requires the GNOME extension.\nInstall the extension from the Advanced tab to enable positioning.")
            position_combo.set_sensitive(False)  # Disable on Wayland without extension
        else:
            if has_extension:
                position_combo.set_tooltip_text("Choose where the recording indicator appears on screen.\n(Enabled via GNOME extension)")
            else:
                position_combo.set_tooltip_text("Choose where the recording indicator appears on screen.")

        grid.attach(position_combo, 1, row, 1, 1)
        row += 1

        # Add warning label for Wayland users without extension
        if is_wayland and not has_extension:
            warning_label = Gtk.Label(label="  ⚠️ Install GNOME extension (Advanced tab) to enable positioning on Wayland", xalign=0)
            warning_label.set_line_wrap(True)
            warning_label.set_max_width_chars(60)
            warning_style = warning_label.get_style_context()
            warning_style.add_class("dim-label")
            grid.attach(warning_label, 0, row, 2, 1)
            row += 1

        # Custom offset X
        offset_x_label = Gtk.Label(label="  Horizontal offset (pixels):", xalign=0)
        grid.attach(offset_x_label, 0, row, 1, 1)

        offset_x_adj = Gtk.Adjustment(value=self.config.get("indicator_offset_x", 0), lower=-1000, upper=1000, step_increment=10)
        offset_x_spin = Gtk.SpinButton(adjustment=offset_x_adj)
        offset_x_spin.set_value(self.config.get("indicator_offset_x", 0))
        offset_x_spin.connect("value-changed", lambda x: self.update_config("indicator_offset_x", int(x.get_value())))
        offset_x_spin.set_tooltip_text("Fine-tune horizontal position.\nPositive = right, Negative = left")
        if is_wayland and not has_extension:
            offset_x_spin.set_sensitive(False)
        grid.attach(offset_x_spin, 1, row, 1, 1)
        row += 1

        # Custom offset Y
        offset_y_label = Gtk.Label(label="  Vertical offset (pixels):", xalign=0)
        grid.attach(offset_y_label, 0, row, 1, 1)

        offset_y_adj = Gtk.Adjustment(value=self.config.get("indicator_offset_y", 0), lower=-1000, upper=1000, step_increment=10)
        offset_y_spin = Gtk.SpinButton(adjustment=offset_y_adj)
        offset_y_spin.set_value(self.config.get("indicator_offset_y", 0))
        offset_y_spin.connect("value-changed", lambda x: self.update_config("indicator_offset_y", int(x.get_value())))
        offset_y_spin.set_tooltip_text("Fine-tune vertical position.\nPositive = down, Negative = up")
        if is_wayland and not has_extension:
            offset_y_spin.set_sensitive(False)
        grid.attach(offset_y_spin, 1, row, 1, 1)
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

        # ===== TEXT FORMATTING SECTION =====
        formatting_header = Gtk.Label()
        formatting_header.set_markup('<b>Text Formatting</b>')
        formatting_header.set_xalign(0)
        formatting_header.set_margin_bottom(10)
        grid.attach(formatting_header, 0, row, 2, 1)
        row += 1

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
        period_check = Gtk.CheckButton(label="Ensure period at end of sentences")
        period_check.set_active(bool(self.config.get("auto_period", True)))  # Ensure boolean, default True
        period_check.connect("toggled", lambda x: self.update_config("auto_period", x.get_active()))
        period_check.set_tooltip_text("Ensure every sentence ends with punctuation.\n\nWhisper AI usually adds periods automatically, but sometimes misses them.\nThis option adds a period when Whisper forgets, ensuring consistent punctuation.\n\nUnchecked: You get whatever Whisper outputs (sometimes has periods, sometimes doesn't)\nChecked: Every sentence is guaranteed to end with punctuation")
        grid.attach(period_check, 0, row, 2, 1)
        row += 1
        
        # Injection mode
        inject_label = Gtk.Label(label="Text Injection 💡:", xalign=0)
        inject_label.set_tooltip_text("How to insert transcribed text:\n• Auto (Smart Detection): Automatically chooses the best method based on the focused app\n• Keystroke Typing: simulates typing character-by-character (most reliable)\n• Clipboard Paste: uses clipboard + Ctrl+V / Shift+Ctrl+V (much faster for long text)\n\nAuto mode intelligently selects:\n✓ Paste for terminals and normal text fields\n✓ Typing for password fields and address bars\n✓ AT-SPI when available and reliable\n\nClipboard Paste works in most applications:\n✓ Text editors, word processors, terminals\n✓ Web browsers, email clients\n✓ Most standard text input fields\n\nUse Keystroke Typing if paste doesn't work in specialized applications.")
        grid.attach(inject_label, 0, row, 1, 1)
        inject_combo = Gtk.ComboBoxText()
        inject_combo.set_can_focus(True)
        inject_combo.connect("button-press-event", self._on_combo_button_press)

        inject_combo.append("auto", "Auto (Smart Detection)")
        inject_combo.append("type", "Keystroke Typing")
        inject_combo.append("paste", "Clipboard Paste")
        inject_combo.set_active_id(self.config["injection_mode"])
        inject_combo.connect("changed", lambda x: self.update_config("injection_mode", x.get_active_id()))
        # Tooltip moved to label to avoid interference with dropdown popup
        grid.attach(inject_combo, 1, row, 1, 1)
        row += 1

        # ===== POWER MANAGEMENT SECTION =====
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(20)
        separator.set_margin_bottom(15)
        grid.attach(separator, 0, row, 2, 1)
        row += 1

        power_header = Gtk.Label()
        power_header.set_markup('<b>Power Management</b>')
        power_header.set_xalign(0)
        power_header.set_margin_bottom(10)
        grid.attach(power_header, 0, row, 2, 1)
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
        self.download_cuda_button.set_tooltip_text("Download CUDA libraries for GPU acceleration (~800MB download)")
        self.download_cuda_button.set_sensitive(False)
        gpu_button_box.pack_start(self.download_cuda_button, False, False, 0)

        grid.attach(gpu_button_box, 0, row, 2, 1)
        row += 1

        # Initial GPU check
        GLib.timeout_add(500, self._initial_gpu_check)

        # Add horizontal separator before Typing Setup section
        separator_typing = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator_typing.set_margin_top(20)
        separator_typing.set_margin_bottom(10)
        grid.attach(separator_typing, 0, row, 2, 1)
        row += 1

        # Typing Setup Section Header
        typing_header = Gtk.Label()
        typing_header.set_markup('<b>⌨️ Typing Setup</b>')
        typing_header.set_xalign(0)
        typing_header.set_margin_bottom(5)
        grid.attach(typing_header, 0, row, 2, 1)
        row += 1

        # Typing Status Label
        self.typing_status_label = Gtk.Label(label="Checking...", xalign=0)
        self.typing_status_label.set_margin_start(10)
        self.typing_status_label.set_margin_bottom(10)
        grid.attach(self.typing_status_label, 0, row, 2, 1)
        row += 1

        # Button box for Typing actions
        typing_button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        typing_button_box.set_margin_start(10)

        # Fix Typing button
        self.fix_typing_button = Gtk.Button(label="🔧 Fix Typing Permissions")
        self.fix_typing_button.connect("clicked", self._on_fix_typing_clicked)
        self.fix_typing_button.set_tooltip_text(
            "Configure system permissions for keystroke injection.\n"
            "Required for typing mode to work. Uses /dev/uinput.\n"
            "Will prompt for admin password."
        )
        self.fix_typing_button.set_sensitive(False)
        typing_button_box.pack_start(self.fix_typing_button, False, False, 0)

        grid.attach(typing_button_box, 0, row, 2, 1)
        row += 1

        # Initial typing check
        GLib.timeout_add(600, self._initial_typing_check)

        # Add horizontal separator before Extensions section
        separator3 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator3.set_margin_top(20)
        separator3.set_margin_bottom(10)
        grid.attach(separator3, 0, row, 2, 1)
        row += 1

        # Extensions Section Header
        extension_header = Gtk.Label()
        extension_header.set_markup('<b>🎨 GNOME Extension</b>')
        extension_header.set_xalign(0)
        extension_header.set_margin_bottom(5)
        grid.attach(extension_header, 0, row, 2, 1)
        row += 1

        # Extension Status Label
        self.extension_status_label = Gtk.Label(label="Checking...", xalign=0)
        self.extension_status_label.set_margin_start(10)
        self.extension_status_label.set_margin_bottom(10)
        grid.attach(self.extension_status_label, 0, row, 2, 1)
        row += 1

        # Button box for Extension actions
        ext_button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        ext_button_box.set_margin_start(10)

        # Install Extension button
        self.install_extension_button = Gtk.Button(label="📦 Install Extension")
        self.install_extension_button.connect("clicked", self._on_install_extension_clicked)
        self.install_extension_button.set_tooltip_text(
            "Download and install GNOME Shell extension (~3KB)\n"
            "Adds panel indicator, service controls, and enables recording indicator positioning on Wayland"
        )
        self.install_extension_button.set_sensitive(False)
        ext_button_box.pack_start(self.install_extension_button, False, False, 0)

        # Uninstall Extension button
        self.uninstall_extension_button = Gtk.Button(label="🗑️ Uninstall Extension")
        self.uninstall_extension_button.connect("clicked", self._on_uninstall_extension_clicked)
        self.uninstall_extension_button.set_tooltip_text("Remove GNOME Shell extension")
        self.uninstall_extension_button.set_sensitive(False)
        ext_button_box.pack_start(self.uninstall_extension_button, False, False, 0)

        # Restart GNOME Shell info button
        self.restart_info_button = Gtk.Button(label="ℹ️ Restart Info")
        self.restart_info_button.connect("clicked", self._on_restart_info_clicked)
        self.restart_info_button.set_tooltip_text("How to restart GNOME Shell to activate extension")
        ext_button_box.pack_start(self.restart_info_button, False, False, 0)

        grid.attach(ext_button_box, 0, row, 2, 1)
        row += 1

        # Initial extension check
        GLib.timeout_add(500, self._initial_extension_check)

        return grid
    
    def create_commands_tab(self):
        """Create the Custom Voice Commands tab."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)
        vbox.set_margin_top(15)
        vbox.set_margin_bottom(15)
        
        # Header
        header = Gtk.Label()
        header.set_markup('<span size="large"><b>Custom Voice Commands</b></span>')
        header.set_xalign(0)
        vbox.pack_start(header, False, False, 0)
        
        # Description
        desc = Gtk.Label()
        desc.set_markup(
            '<span size="small">Define custom phrases that will be replaced during dictation.\n'
            'For example: say "my email" → inserts "user@example.com"</span>'
        )
        desc.set_xalign(0)
        desc.set_line_wrap(True)
        vbox.pack_start(desc, False, False, 5)

        # Buttons for add/remove (at the top for easy access)
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_margin_top(5)
        button_box.set_margin_bottom(5)

        add_btn = Gtk.Button(label="➕ Add Command")
        add_btn.connect("clicked", self._on_add_command)
        add_btn.set_tooltip_text("Add a new custom voice command")
        button_box.pack_start(add_btn, False, False, 0)

        remove_btn = Gtk.Button(label="➖ Remove Selected")
        remove_btn.connect("clicked", self._on_remove_command)
        remove_btn.set_tooltip_text("Remove the selected command")
        button_box.pack_start(remove_btn, False, False, 0)

        vbox.pack_start(button_box, False, False, 0)

        # Create list store for commands: phrase, replacement
        self.commands_store = Gtk.ListStore(str, str)

        # Load existing commands
        commands = load_custom_commands()
        for phrase, replacement in commands.items():
            self.commands_store.append([phrase, replacement])

        # Create tree view
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        # Set reasonable height limits - grows with content but doesn't fill empty space
        scrolled.set_min_content_height(160)  # Show ~5 rows minimum for easier browsing
        scrolled.set_max_content_height(280)  # Cap at ~10 rows so tips stay visible

        self.commands_tree = Gtk.TreeView(model=self.commands_store)
        self.commands_tree.set_headers_visible(True)

        # Phrase column (editable)
        phrase_renderer = Gtk.CellRendererText()
        phrase_renderer.set_property("editable", True)
        phrase_renderer.connect("edited", self._on_phrase_edited)
        phrase_renderer.connect("editing-started", self._on_cell_editing_started, 0)
        phrase_column = Gtk.TreeViewColumn("Spoken Phrase", phrase_renderer, text=0)
        phrase_column.set_expand(True)
        phrase_column.set_min_width(150)
        self.commands_tree.append_column(phrase_column)

        # Replacement column (editable)
        replacement_renderer = Gtk.CellRendererText()
        replacement_renderer.set_property("editable", True)
        replacement_renderer.connect("edited", self._on_replacement_edited)
        replacement_renderer.connect("editing-started", self._on_cell_editing_started, 1)
        replacement_column = Gtk.TreeViewColumn("Replacement Text", replacement_renderer, text=1)
        replacement_column.set_expand(True)
        replacement_column.set_min_width(200)
        self.commands_tree.append_column(replacement_column)

        scrolled.add(self.commands_tree)
        vbox.pack_start(scrolled, False, False, 0)  # Don't expand - stay compact
        
        # Tips section
        tips = Gtk.Label()
        tips.set_markup(
            '<span size="small"><b>Tips:</b>\n'
            '• Click on a cell to edit it directly\n'
            '• Phrases are matched case-insensitively\n'
            '• Use \\n in replacement for line breaks\n'
            '• Changes are saved when you click Apply or OK\n'
            '• Restart the dictation service for changes to take effect</span>'
        )
        tips.set_xalign(0)
        tips.set_line_wrap(True)
        vbox.pack_start(tips, False, False, 10)
        
        return vbox

    def create_updates_tab(self):
        """Create the Updates tab for checking for software updates."""
        import threading
        from . import update_checker

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)
        vbox.set_margin_top(15)
        vbox.set_margin_bottom(15)

        # Header
        header = Gtk.Label()
        header.set_markup('<span size="large"><b>Software Updates</b></span>')
        header.set_xalign(0)
        vbox.pack_start(header, False, False, 0)

        # Current versions section
        version_frame = Gtk.Frame(label="Current Versions")
        version_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        version_box.set_margin_start(10)
        version_box.set_margin_end(10)
        version_box.set_margin_top(10)
        version_box.set_margin_bottom(10)

        # AppImage version
        current_version = update_checker.get_current_version()
        self.app_version_label = Gtk.Label()
        self.app_version_label.set_markup(f"<b>TalkType:</b> {current_version}")
        self.app_version_label.set_xalign(0)
        version_box.pack_start(self.app_version_label, False, False, 0)

        # Extension version
        ext_version = update_checker.get_extension_version()
        ext_text = f"Version {ext_version}" if ext_version else "Not installed"
        self.ext_version_label = Gtk.Label()
        self.ext_version_label.set_markup(f"<b>GNOME Extension:</b> {ext_text}")
        self.ext_version_label.set_xalign(0)
        version_box.pack_start(self.ext_version_label, False, False, 0)

        version_frame.add(version_box)
        vbox.pack_start(version_frame, False, False, 10)

        # Check for updates button
        check_btn = Gtk.Button(label="Check for Updates")
        check_btn.set_halign(Gtk.Align.START)
        check_btn.connect("clicked", self._on_check_updates_clicked)
        vbox.pack_start(check_btn, False, False, 5)

        # Status area (hidden initially)
        self.update_status_frame = Gtk.Frame(label="Update Status")
        self.update_status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.update_status_box.set_margin_start(10)
        self.update_status_box.set_margin_end(10)
        self.update_status_box.set_margin_top(10)
        self.update_status_box.set_margin_bottom(10)

        self.update_status_label = Gtk.Label(label="Click 'Check for Updates' to check for new versions.")
        self.update_status_label.set_xalign(0)
        self.update_status_label.set_line_wrap(True)
        self.update_status_box.pack_start(self.update_status_label, False, False, 0)

        # Buttons for update actions (hidden initially)
        self.update_actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.update_actions_box.set_margin_top(10)

        self.download_btn = Gtk.Button(label="Download & Install")
        self.download_btn.connect("clicked", self._on_download_update_clicked)
        self.download_btn.set_no_show_all(True)
        self.download_btn.set_tooltip_text("Download the update and automatically install & restart TalkType")
        self.update_actions_box.pack_start(self.download_btn, False, False, 0)

        self.view_release_btn = Gtk.Button(label="View on GitHub")
        self.view_release_btn.connect("clicked", self._on_view_release_clicked)
        self.view_release_btn.set_no_show_all(True)
        self.update_actions_box.pack_start(self.view_release_btn, False, False, 0)

        # Update Extension button (only relevant for GNOME users with extension installed)
        self.update_extension_btn = Gtk.Button(label="Update Extension")
        self.update_extension_btn.connect("clicked", self._on_update_extension_clicked)
        self.update_extension_btn.set_no_show_all(True)
        self.update_actions_box.pack_start(self.update_extension_btn, False, False, 0)

        self.update_status_box.pack_start(self.update_actions_box, False, False, 0)
        self.update_status_frame.add(self.update_status_box)
        vbox.pack_start(self.update_status_frame, False, False, 10)

        # Store release info for download button
        self._current_release = None

        # Auto-check option
        auto_check_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        auto_check_box.set_margin_top(10)

        auto_check_toggle = Gtk.CheckButton(label="Automatically check for updates on startup")
        auto_check_toggle.set_active(self.config.get("auto_check_updates", True))
        auto_check_toggle.connect("toggled", lambda x: self.update_config("auto_check_updates", x.get_active()))
        auto_check_toggle.set_tooltip_text(
            "When enabled, TalkType will check for updates once per day when it starts.\n"
            "If an update is found, you'll be notified and the Updates tab will open."
        )
        auto_check_box.pack_start(auto_check_toggle, False, False, 0)

        vbox.pack_start(auto_check_box, False, False, 5)

        # Info text
        info_label = Gtk.Label()
        info_label.set_markup(
            '<span size="small"><b>AppImage location:</b> ~/AppImages/TalkType.AppImage\n'
            'Updates are downloaded, installed, and TalkType restarts automatically.</span>'
        )
        info_label.set_xalign(0)
        info_label.set_line_wrap(True)
        vbox.pack_start(info_label, False, False, 10)

        # Full changelog link
        changelog_link = Gtk.LinkButton.new_with_label(
            update_checker.get_releases_url(),
            "View Full Changelog on GitHub"
        )
        changelog_link.set_halign(Gtk.Align.START)
        vbox.pack_start(changelog_link, False, False, 5)

        return vbox

    def _on_check_updates_clicked(self, button):
        """Handle check for updates button click."""
        import threading
        from . import update_checker

        # Update status and hide action buttons
        self.update_status_label.set_text("Checking for updates...")
        self.download_btn.hide()
        self.view_release_btn.hide()
        self.update_extension_btn.hide()
        button.set_sensitive(False)

        def do_check():
            result = update_checker.check_for_updates()
            GLib.idle_add(lambda: self._handle_update_result(result, button))

        thread = threading.Thread(target=do_check, daemon=True)
        thread.start()

    def _handle_update_result(self, result, button):
        """Handle update check result in main thread."""
        button.set_sensitive(True)

        if not result.get("success"):
            self.update_status_label.set_markup(
                f"<span color='red'>Check failed: {result.get('error', 'Unknown error')}</span>"
            )
            return

        has_update = result.get("update_available", False)
        has_ext_update = result.get("extension_update", False)
        current = result.get("current_version", "unknown")
        latest = result.get("latest_version", "unknown")
        ext_current = result.get("extension_current")
        ext_latest = result.get("extension_latest")
        release = result.get("release", {})

        self._current_release = release

        # Build status message
        if has_update:
            status_lines = [
                f"<span color='#4CAF50'><b>Update available!</b></span>",
                f"TalkType: {current} → <b>{latest}</b>"
            ]
        else:
            status_lines = [
                f"<span color='#4CAF50'>You're up to date!</span>",
                f"TalkType {current} is the latest version."
            ]

        # Add extension status
        if ext_current is not None:
            if has_ext_update:
                status_lines.append(f"Extension: {ext_current} → <b>{ext_latest}</b> (update available)")
                status_lines.append("<span size='small'>Note: Extension updates require logout/login</span>")
            else:
                status_lines.append(f"Extension: Version {ext_current} (up to date)")

        self.update_status_label.set_markup("\n".join(status_lines))

        # Show/hide buttons based on available updates
        if has_update:
            if release.get("appimage_url"):
                self.download_btn.show()
            if release.get("html_url"):
                self.view_release_btn.show()
        else:
            self.download_btn.hide()
            self.view_release_btn.hide()

        # Show extension update button if extension update available
        if has_ext_update:
            self.update_extension_btn.show()
        else:
            self.update_extension_btn.hide()

    def _on_download_update_clicked(self, button):
        """Handle download update button click - downloads, installs, and restarts."""
        import threading
        from . import update_checker

        if not self._current_release:
            return

        url = self._current_release.get("appimage_url")
        filename = self._current_release.get("appimage_name", "TalkType-update.AppImage")

        if not url:
            return

        # Confirm with user
        confirm_dialog = Gtk.MessageDialog(
            transient_for=self.window,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Download & Install Update?"
        )
        confirm_dialog.format_secondary_text(
            "TalkType will:\n"
            "1. Download the new version\n"
            "2. Install it to ~/AppImages/TalkType.AppImage\n"
            "3. Restart automatically\n\n"
            "Any unsaved preferences changes will be saved first."
        )
        response = confirm_dialog.run()
        confirm_dialog.destroy()

        if response != Gtk.ResponseType.YES:
            return

        # Save any pending config changes first
        self.save_config()

        # Create progress dialog
        progress_dialog = Gtk.Dialog(
            title="Updating TalkType",
            transient_for=self.window,
            flags=Gtk.DialogFlags.MODAL
        )
        progress_dialog.set_default_size(400, 120)
        progress_dialog.set_deletable(False)  # Prevent closing during update

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

        result_holder = {"download_path": None, "error": None}

        def progress_callback(message, percent):
            GLib.idle_add(lambda: status_label.set_text(message))
            GLib.idle_add(lambda: progress_bar.set_fraction(percent / 100.0))
            GLib.idle_add(lambda: progress_bar.set_text(f"{percent}%"))

        def do_download_and_install():
            # Step 1: Download
            downloaded_path = update_checker.download_update(url, filename, progress_callback)

            if not downloaded_path:
                result_holder["error"] = "Download failed"
                GLib.idle_add(download_failed)
                return

            result_holder["download_path"] = downloaded_path

            # Step 2: Install and restart
            GLib.idle_add(lambda: status_label.set_text("Installing update..."))
            GLib.idle_add(lambda: progress_bar.set_fraction(0.9))

            success, message = update_checker.install_update_and_restart(
                downloaded_path,
                progress_callback
            )

            # If we get here, something went wrong (install_update_and_restart should exec)
            if not success:
                result_holder["error"] = message
                GLib.idle_add(download_failed)

        def download_failed():
            progress_dialog.destroy()

            error_msg = result_holder.get("error", "Unknown error")
            self.update_status_label.set_markup(
                f"<span color='red'>Update failed: {error_msg}</span>\n"
                f"Please try again or download manually from GitHub."
            )

            # Show error dialog
            dialog = Gtk.MessageDialog(
                transient_for=self.window,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Update Failed"
            )
            dialog.format_secondary_text(
                f"{error_msg}\n\n"
                f"You can try again or download the update manually from GitHub."
            )
            dialog.run()
            dialog.destroy()

        thread = threading.Thread(target=do_download_and_install, daemon=True)
        thread.start()

    def _on_view_release_clicked(self, button):
        """Open the release page on GitHub."""
        from . import update_checker

        if self._current_release and self._current_release.get("html_url"):
            update_checker.open_release_page(self._current_release["html_url"])

    def _on_update_extension_clicked(self, button):
        """Handle Update Extension button click - downloads and installs latest extension."""
        import threading
        from . import extension_helper

        # Create progress dialog
        progress_dialog = Gtk.Dialog(
            title="Updating Extension",
            transient_for=self.window,
            flags=Gtk.DialogFlags.MODAL
        )
        progress_dialog.set_default_size(350, 100)

        content = progress_dialog.get_content_area()
        content.set_spacing(10)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(10)

        status_label = Gtk.Label(label="Downloading extension...")
        status_label.set_halign(Gtk.Align.START)
        content.pack_start(status_label, False, False, 0)

        progress_bar = Gtk.ProgressBar()
        progress_bar.set_show_text(True)
        content.pack_start(progress_bar, False, False, 10)

        progress_dialog.show_all()

        success_holder = [False]

        def progress_callback(message, percent):
            """Update progress in main thread."""
            def update_ui():
                status_label.set_text(message)
                progress_bar.set_fraction(percent / 100.0)
                progress_bar.set_text(f"{percent}%")
                return False
            GLib.idle_add(update_ui)

        def do_install():
            """Background thread to install extension."""
            success_holder[0] = extension_helper.download_and_install_extension(progress_callback)
            GLib.idle_add(finish_install)

        def finish_install():
            """Finish up in main thread."""
            progress_dialog.destroy()

            if success_holder[0]:
                # Success dialog
                success_dialog = Gtk.MessageDialog(
                    transient_for=self.window,
                    message_type=Gtk.MessageType.INFO,
                    buttons=Gtk.ButtonsType.OK,
                    text="Extension Updated!"
                )
                success_dialog.format_secondary_text(
                    "The GNOME extension has been updated.\n\n"
                    "You need to log out and log back in for the changes to take effect."
                )
                success_dialog.run()
                success_dialog.destroy()

                # Update UI to reflect new state
                self.update_extension_btn.hide()
                self.update_status_label.set_markup(
                    "<span color='#4CAF50'>Extension updated!</span>\n"
                    "Log out and log back in to activate the new version."
                )
            else:
                # Error dialog
                error_dialog = Gtk.MessageDialog(
                    transient_for=self.window,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Update Failed"
                )
                error_dialog.format_secondary_text(
                    "Failed to update the GNOME extension.\n"
                    "Check the log file for details."
                )
                error_dialog.run()
                error_dialog.destroy()

        # Start installation in background
        thread = threading.Thread(target=do_install, daemon=True)
        thread.start()

    def _on_cell_editing_started(self, renderer, editable, path, column_idx):
        """Handle when a cell starts being edited - setup focus-out commit and Tab navigation."""
        # Store current editing state
        self._current_edit_path = path
        self._current_edit_column = column_idx
        
        # Connect to focus-out to commit the edit
        def on_focus_out(widget, event):
            # Commit the current text
            text = widget.get_text()
            if column_idx == 0:
                self._on_phrase_edited(renderer, path, text)
            else:
                self._on_replacement_edited(renderer, path, text)
            return False
        
        editable.connect("focus-out-event", on_focus_out)
        
        # Handle Tab key to move to next column/row
        def on_key_press(widget, event):
            from gi.repository import Gdk
            if event.keyval == Gdk.KEY_Tab:
                # Commit current edit first
                text = widget.get_text()
                if column_idx == 0:
                    self._on_phrase_edited(renderer, path, text)
                else:
                    self._on_replacement_edited(renderer, path, text)
                
                # Stop the current edit
                widget.editing_done()
                widget.remove_widget()
                
                # Move to next column or next row
                if column_idx == 0:
                    # Move to replacement column (column 1)
                    GLib.idle_add(lambda: self.commands_tree.set_cursor(
                        Gtk.TreePath.new_from_string(path),
                        self.commands_tree.get_column(1),
                        True
                    ))
                else:
                    # Move to next row's phrase column (column 0)
                    current_path = Gtk.TreePath.new_from_string(path)
                    next_idx = current_path.get_indices()[0] + 1
                    if next_idx < len(self.commands_store):
                        GLib.idle_add(lambda: self.commands_tree.set_cursor(
                            Gtk.TreePath.new_from_indices([next_idx]),
                            self.commands_tree.get_column(0),
                            True
                        ))
                return True  # Consume the Tab event
            return False
        
        editable.connect("key-press-event", on_key_press)
    
    def _on_phrase_edited(self, renderer, path, new_text):
        """Handle editing of the phrase column."""
        if new_text.strip():
            self.commands_store[path][0] = new_text.strip().lower()
    
    def _on_replacement_edited(self, renderer, path, new_text):
        """Handle editing of the replacement column."""
        self.commands_store[path][1] = new_text
    
    def _on_add_command(self, button):
        """Add a new empty command row."""
        iter = self.commands_store.append(["new phrase", "replacement text"])
        # Select the new row
        path = self.commands_store.get_path(iter)
        self.commands_tree.set_cursor(path, self.commands_tree.get_column(0), True)
    
    def _on_remove_command(self, button):
        """Remove the selected command."""
        selection = self.commands_tree.get_selection()
        model, iter = selection.get_selected()
        if iter:
            model.remove(iter)
    
    def _save_custom_commands(self):
        """Save custom commands from the list store."""
        commands = {}
        for row in self.commands_store:
            phrase = row[0].strip().lower()
            replacement = row[1]
            if phrase:  # Only save non-empty phrases
                commands[phrase] = replacement
        save_custom_commands(commands)
    
    def _on_combo_button_press(self, widget, event):
        """Handle button press events on combo boxes to ensure they open reliably."""
        # Ensure the widget has focus before processing the click
        if not widget.has_focus():
            widget.grab_focus()
        # Let GTK handle the normal click event
        return False

    def update_config(self, key, value):
        """Update config value."""
        # Special handling for device changes - verify CUDA is available
        if key == "device" and value == "cuda":
            from talktype import cuda_helper
            if not cuda_helper.has_cuda_libraries():
                # CUDA libraries not available - show error and revert to CPU
                dialog = Gtk.MessageDialog(
                    transient_for=self.window,
                    flags=0,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="CUDA Libraries Not Available"
                )
                dialog.format_secondary_text(
                    "GPU acceleration requires CUDA libraries to be downloaded first.\n\n"
                    "Please download CUDA libraries from the Advanced tab before switching to GPU mode."
                )
                dialog.run()
                dialog.destroy()

                # Revert combo box to CPU
                if hasattr(self, 'device_combo'):
                    self.device_combo.set_active_id("cpu")
                return  # Don't update config

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

        # Track last selected model to avoid showing dialog when clicking same model
        if not hasattr(self, '_last_selected_model'):
            self._last_selected_model = self.config.get("model")

        # Show warning dialog for large-v3 model ONLY if it's not already downloaded
        from .model_helper import is_model_cached
        if new_model == "large-v3" and not is_model_cached("large-v3"):
            dialog = Gtk.MessageDialog(
                transient_for=self.window,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK_CANCEL,
                text="Large Model Selected"
            )

            # Apply dark theme
            settings = Gtk.Settings.get_default()
            if settings:
                settings.set_property("gtk-application-prefer-dark-theme", True)

            dialog.format_secondary_text(
                "The large-v3 model is approximately 3 GB in size.\n\n"
                "⏱️  First-time load: 30-60 seconds\n"
                "⏱️  Subsequent loads: 10-20 seconds\n\n"
                "The application will not respond to your dictation hotkey "
                "until the model has fully loaded.\n\n"
                "💡 Click OK here to confirm, then click Apply or OK in Preferences to start the download.\n\n"
                "Do you want to proceed with this model?"
            )

            response = dialog.run()
            dialog.destroy()

            if response == Gtk.ResponseType.CANCEL:
                # Revert to previous model selection (block recursive call)
                self._updating_model = True
                combo.set_active_id(self._last_selected_model)
                self._updating_model = False
                return

        # Update config with new model and track it
        self._last_selected_model = new_model
        self.update_config("model", new_model)

    def _handle_autostart(self, enable):
        """Create or remove autostart desktop file."""
        from . import config

        autostart_dir = os.path.expanduser("~/.config/autostart")
        # Use different filename for dev mode vs production
        filename = "talktype-dev.desktop" if config.DEV_MODE else "talktype.desktop"
        desktop_file = os.path.join(autostart_dir, filename)

        if enable:
            # Create autostart directory if it doesn't exist
            os.makedirs(autostart_dir, exist_ok=True)

            # Determine the best way to launch TalkType
            # Priority: 1. Use dictate-tray if available, 2. Use current Python
            exec_cmd = self._get_launch_command()
            icon_path = self._get_icon_path()

            # Create desktop file content
            app_name = "TalkType (Dev)" if config.DEV_MODE else "TalkType"
            comment = "AI-powered dictation - Development Version" if config.DEV_MODE else "AI-powered dictation for Wayland using Faster-Whisper"

            # For dev mode, add Path directive so run-dev.sh works correctly
            path_line = ""
            if config.DEV_MODE:
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                path_line = f"Path={project_root}\n"

            desktop_content = f"""[Desktop Entry]
Type=Application
Name={app_name}
GenericName=Voice Dictation
Comment={comment}
Exec={exec_cmd}
Icon={icon_path}
Terminal=false
Categories=Utility;
Keywords=dictation;voice;speech;whisper;ai;transcription;
StartupNotify=true
StartupWMClass=TalkType
X-GNOME-Autostart-enabled=true
{path_line}"""

            try:
                with open(desktop_file, "w") as f:
                    f.write(desktop_content)
                print(f"✅ Created autostart file: {desktop_file}")
                print(f"   Launch command: {exec_cmd}")
            except Exception as e:
                print(f"❌ Failed to create autostart file: {e}")
        else:
            # Disable autostart using XDG standard Hidden=true
            # This is more reliable than deleting, especially on KDE which caches entries
            try:
                os.makedirs(autostart_dir, exist_ok=True)

                # Write a minimal desktop file with Hidden=true to disable autostart
                # This overrides any existing entry and tells the DE to ignore it
                disabled_content = f"""[Desktop Entry]
Type=Application
Name=TalkType
Hidden=true
"""
                with open(desktop_file, "w") as f:
                    f.write(disabled_content)
                print(f"✅ Disabled autostart: {desktop_file}")
            except Exception as e:
                print(f"❌ Failed to disable autostart file: {e}")

    def _get_launch_command(self):
        """
        Get the appropriate launch command for TalkType.

        Returns the most portable way to launch the tray icon:
        1. If running in DEV_MODE, use the run-dev.sh script
        2. If running from AppImage, use the AppImage path
        3. If dictate-tray is in PATH, use it (works for installed versions)
        4. Otherwise, use the current Python interpreter with the module path
        """
        # Check if we're in DEV_MODE - use run-dev.sh script
        from . import config
        if config.DEV_MODE:
            # Find the run-dev.sh script relative to this file
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            run_dev_script = os.path.join(project_root, 'run-dev.sh')
            if os.path.isfile(run_dev_script) and os.access(run_dev_script, os.X_OK):
                return run_dev_script
            else:
                # Fallback for dev mode - use bash with env vars
                return f'/bin/bash -c "cd {project_root} && DEV_MODE=1 PYTHONPATH=./src:/usr/lib64/python3.13/site-packages:/usr/lib/python3.13/site-packages {sys.executable} -m talktype.tray"'

        # Check if we're running from an AppImage
        appimage_path = os.environ.get('APPIMAGE')
        if appimage_path and os.path.isfile(appimage_path) and os.access(appimage_path, os.X_OK):
            # Return the AppImage path - it defaults to starting the tray
            return appimage_path

        # Check if sys.executable is inside an AppImage mount point
        # (handles cases where APPIMAGE env var might not be set but we're still in an AppImage)
        if '/tmp/.mount_' in sys.executable or 'squashfs-root' in sys.executable:
            # Try to find the AppImage in common locations
            possible_appimages = [
                os.path.expanduser('~/AppImages/TalkType-*.AppImage'),
                os.path.expanduser('~/Downloads/TalkType-*.AppImage'),
            ]
            import glob
            for pattern in possible_appimages:
                matches = glob.glob(pattern)
                if matches:
                    # Use the most recent one
                    latest = max(matches, key=os.path.getmtime)
                    if os.access(latest, os.X_OK):
                        return latest

        # Check if dictate-tray command is available in PATH
        try:
            result = subprocess.run(
                ['which', 'dictate-tray'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                dictate_tray_path = result.stdout.strip()
                # Verify it's executable
                if os.path.isfile(dictate_tray_path) and os.access(dictate_tray_path, os.X_OK):
                    return dictate_tray_path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fallback: use current Python interpreter
        python_path = sys.executable
        # Use -m to run as module, which is more reliable
        return f'{python_path} -m talktype.tray'

    def _get_icon_path(self):
        """
        Get the path to the TalkType icon.

        Returns:
            str: Path to icon file, or fallback to system icon name
        """
        # Try common locations
        possible_paths = [
            # Official icon in development location (Dropbox)
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'icons', 'OFFICIAL_ICON_DO_NOT_CHANGE.svg'),
            # AppImage location
            os.path.join(os.path.dirname(sys.executable), '..', 'io.github.ronb1964.TalkType.svg'),
            # Old development location (AppDir)
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'AppDir', 'io.github.ronb1964.TalkType.svg'),
            # Installed location
            '/usr/share/icons/hicolor/scalable/apps/io.github.ronb1964.TalkType.svg',
            '/usr/local/share/icons/hicolor/scalable/apps/io.github.ronb1964.TalkType.svg',
        ]

        for path in possible_paths:
            if os.path.isfile(path):
                return os.path.abspath(path)

        # Fallback to system icon name
        return 'audio-input-microphone'

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
                import numpy as np

                # Amplify the audio for better playback volume (3x boost)
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
        """
        Get the current system microphone volume.
        Supports both PipeWire (wpctl) and PulseAudio (pactl).
        """
        import subprocess

        # Try PipeWire first (modern systems like Fedora, Nobara, newer Ubuntu)
        try:
            result = subprocess.run(
                ["wpctl", "get-volume", "@DEFAULT_AUDIO_SOURCE@"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                # Parse volume from output like "Volume: 0.90" or "Volume: 0.90 [MUTED]"
                output = result.stdout.strip()
                if 'Volume:' in output:
                    # Extract the decimal value (0.0 to 1.0)
                    parts = output.split()
                    if len(parts) >= 2:
                        try:
                            volume_decimal = float(parts[1])
                            return int(volume_decimal * 100)  # Convert to percentage
                        except ValueError:
                            pass
        except FileNotFoundError:
            # wpctl not installed - try PulseAudio
            pass
        except Exception as e:
            print(f"wpctl failed: {e}")

        # Try PulseAudio (older/traditional systems)
        try:
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
            # pactl not installed either
            pass
        except Exception as e:
            print(f"pactl failed: {e}")

        # Fallback to 50% if neither wpctl nor pactl work
        return 50
    
    def set_system_mic_volume(self, volume_percent):
        """
        Set the system microphone volume.
        Supports both PipeWire (wpctl) and PulseAudio (pactl).
        """
        import subprocess

        # Try PipeWire first (modern systems)
        try:
            # wpctl expects decimal format (0.0 to 1.0)
            volume_decimal = volume_percent / 100.0
            result = subprocess.run(
                ["wpctl", "set-volume", "@DEFAULT_AUDIO_SOURCE@", f"{volume_decimal}"],
                capture_output=True, timeout=2
            )
            if result.returncode == 0:
                return  # Success!
        except FileNotFoundError:
            # wpctl not installed - try PulseAudio
            pass
        except Exception as e:
            print(f"wpctl failed: {e}")

        # Try PulseAudio (older systems)
        try:
            subprocess.run(
                ["pactl", "set-source-volume", "@DEFAULT_SOURCE@", f"{volume_percent}%"],
                capture_output=True, timeout=2
            )
            return  # Success!
        except FileNotFoundError:
            # Neither wpctl nor pactl available
            print("Volume control not available (neither wpctl nor pactl found)")
        except Exception as e:
            print(f"pactl failed: {e}")
    
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
            # Use has_talktype_cuda_libraries() for UI display (not system CUDA)
            has_cuda = cuda_helper.has_talktype_cuda_libraries()
            
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

        # Show confirmation dialog first
        confirm_dialog = Gtk.MessageDialog(
            parent=self.window,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Download CUDA Libraries?"
        )

        # Apply dark theme to dialog
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-application-prefer-dark-theme", True)

        from talktype.config import get_data_dir
        cuda_path = os.path.join(get_data_dir(), "cuda")
        confirm_dialog.format_secondary_text(
            "This will download approximately 800MB of CUDA libraries for GPU acceleration.\n\n"
            f"The files will be stored in {cuda_path} and may take several minutes to download.\n\n"
            "Continue with download?"
        )

        response = confirm_dialog.run()
        confirm_dialog.destroy()

        # If user clicked No, cancel
        if response != Gtk.ResponseType.YES:
            return

        # Disable button during download
        button.set_sensitive(False)

        # Define callback to refresh UI after successful download
        def on_success():
            """Refresh UI elements after successful CUDA download"""
            # Refresh GPU status
            self._check_gpu_status()

            # Refresh device dropdown to show CUDA option
            self._refresh_device_options()

            # Update device combo to reflect change and auto-save config
            if hasattr(self, 'device_combo'):
                self.device_combo.set_active_id("cuda")
                # Auto-save to config so tray and service see the change
                self.config["device"] = "cuda"
                self.save_config()
                print("✅ Automatically switched to GPU mode after CUDA download")

        # Show the modern download dialog
        success = cuda_helper.show_cuda_download_dialog(
            parent=self.window,
            on_success_callback=on_success
        )

        # Re-enable button if download failed
        if not success:
            button.set_sensitive(True)

    def _initial_typing_check(self):
        """Perform initial typing permission check when preferences window opens."""
        self._check_typing_status()
        return False  # Don't repeat

    def _check_typing_status(self):
        """Check typing permission status and update UI."""
        try:
            from . import uinput_helper
            
            has_access, reason = uinput_helper.check_uinput_permission()
            
            if has_access:
                self.typing_status_label.set_markup(
                    '<span color="#4CAF50">✓ Typing permissions configured correctly</span>'
                )
                self.fix_typing_button.set_label("✓ Ready")
                self.fix_typing_button.set_sensitive(False)
            else:
                # Check if udev rule exists (might need reboot)
                if uinput_helper.check_udev_rule_exists():
                    self.typing_status_label.set_markup(
                        '<span color="#FF9800">⚠ Permissions configured - please log out and back in</span>'
                    )
                    self.fix_typing_button.set_label("✓ Configured")
                    self.fix_typing_button.set_sensitive(False)
                else:
                    self.typing_status_label.set_markup(
                        '<span color="#FF9800">⚠ Typing permissions not configured (using Clipboard mode as fallback)</span>'
                    )
                    self.fix_typing_button.set_sensitive(True)
                    
        except ImportError:
            self.typing_status_label.set_markup(
                '<span color="#9E9E9E">⊘ Typing check not available</span>'
            )
            self.fix_typing_button.set_sensitive(False)
        except Exception as e:
            self.typing_status_label.set_text(f"Error checking typing: {e}")
            print(f"Typing check error: {e}")

    def _on_fix_typing_clicked(self, button):
        """Handle Fix Typing button click."""
        try:
            from . import uinput_helper
            
            # Show confirmation dialog
            dialog = Gtk.MessageDialog(
                transient_for=self.window,
                flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Configure Typing Permissions?"
            )
            dialog.format_secondary_text(
                "This will configure system permissions to allow TalkType to type "
                "directly into applications.\n\n"
                "What this does:\n"
                "• Adds a udev rule for /dev/uinput access\n"
                "• Adds your user to the 'input' group\n\n"
                "You will be prompted for your admin password.\n\n"
                "After setup, you'll need to log out and log back in for "
                "the changes to take effect.\n\n"
                "Continue?"
            )
            
            response = dialog.run()
            dialog.destroy()
            
            if response != Gtk.ResponseType.YES:
                return
            
            # Disable button during fix
            button.set_sensitive(False)
            button.set_label("Setting up...")
            
            # Run the fix
            success, message = uinput_helper.install_udev_rule_with_pkexec(self.window)
            
            if success:
                # Show success dialog
                msg = Gtk.MessageDialog(
                    transient_for=self.window,
                    modal=True,
                    message_type=Gtk.MessageType.INFO,
                    buttons=Gtk.ButtonsType.OK,
                    text="Typing Permissions Configured!"
                )
                msg.format_secondary_text(
                    "The system has been configured for keystroke injection.\n\n"
                    "IMPORTANT: Log out and back in to apply the changes.\n"
                    "(Some systems may require a full reboot instead.)\n\n"
                    "After that, TalkType will be able to type "
                    "directly into your applications."
                )
                msg.run()
                msg.destroy()
                
                # Update status
                self._check_typing_status()
            else:
                # Re-enable button
                button.set_sensitive(True)
                button.set_label("🔧 Fix Typing Permissions")
                
                if "cancelled" not in message.lower():
                    # Show error dialog
                    msg = Gtk.MessageDialog(
                        transient_for=self.window,
                        modal=True,
                        message_type=Gtk.MessageType.ERROR,
                        buttons=Gtk.ButtonsType.OK,
                        text="Setup Failed"
                    )
                    msg.format_secondary_text(message)
                    msg.run()
                    msg.destroy()
                    
        except Exception as e:
            print(f"Error fixing typing permissions: {e}")
            button.set_sensitive(True)
            button.set_label("🔧 Fix Typing Permissions")

    def _initial_extension_check(self):
        """Perform initial extension check when preferences window opens."""
        self._check_extension_status()
        return False  # Don't repeat

    def _check_extension_status(self):
        """Check extension status and update UI."""
        try:
            # Import extension_helper
            try:
                from . import extension_helper
            except ImportError:
                self.extension_status_label.set_text("Extension support not available")
                self.install_extension_button.set_sensitive(False)
                self.uninstall_extension_button.set_sensitive(False)
                return

            # Get extension status
            status = extension_helper.get_extension_status()

            if not status['available']:
                self.extension_status_label.set_markup('<span color="#9E9E9E">⊘ Not available (requires GNOME desktop)</span>')
                self.install_extension_button.set_sensitive(False)
                self.uninstall_extension_button.set_sensitive(False)
            elif status['installed']:
                if status['enabled']:
                    self.extension_status_label.set_markup('<span color="#4CAF50">✓ Extension installed and enabled</span>')
                else:
                    self.extension_status_label.set_markup('<span color="#FF9800">⚠ Extension installed but not enabled</span>')
                self.install_extension_button.set_label("✓ Installed")
                self.install_extension_button.set_sensitive(False)
                self.uninstall_extension_button.set_sensitive(True)
            else:
                self.extension_status_label.set_markup('<span color="#FF9800">⊘ Extension not installed</span>')
                self.install_extension_button.set_sensitive(True)
                self.uninstall_extension_button.set_sensitive(False)

        except Exception as e:
            self.extension_status_label.set_text(f"Error checking extension: {e}")
            print(f"Extension check error: {e}")

    def _on_install_extension_clicked(self, button):
        """Handle Install Extension button click."""
        try:
            from . import extension_helper
        except ImportError:
            return

        # Show confirmation dialog
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Install GNOME Extension?"
        )
        dialog.format_secondary_markup(
            "<b>TalkType GNOME Shell Extension</b>\n\n"
            "✨ <b>Features:</b>\n"
            "  • Panel indicator with recording status\n"
            "  • Active model and device display (read-only)\n"
            "  • Enables custom recording indicator positioning on Wayland\n"
            "  • Native GNOME integration with service controls\n\n"
            "📦 <b>Size:</b> ~3KB\n\n"
            "⚠️  <b>Note:</b> You'll need to restart GNOME Shell after installation:\n"
            "    Press Alt+F2, type 'r', press Enter\n\n"
            "Install now?"
        )

        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            # Create progress dialog
            progress_dialog = Gtk.Dialog(
                title="Installing Extension",
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
            status_label = Gtk.Label(label="Preparing installation...")
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

            def install_thread():
                """Run installation in background thread."""
                success = extension_helper.download_and_install_extension(progress_callback)

                def finish_install():
                    progress_dialog.destroy()

                    if success:
                        # Refresh extension status
                        self._check_extension_status()

                        # Show success dialog with restart instructions
                        success_dialog = Gtk.MessageDialog(
                            transient_for=self.window,
                            flags=0,
                            message_type=Gtk.MessageType.INFO,
                            buttons=Gtk.ButtonsType.OK,
                            text="Extension Installed Successfully!"
                        )
                        success_dialog.format_secondary_markup(
                            "<b>Next Steps:</b>\n\n"
                            "1. Restart GNOME Shell to activate the extension:\n"
                            "   • Press <b>Alt+F2</b>\n"
                            "   • Type <b>r</b> and press <b>Enter</b>\n"
                            "   • OR log out and log back in\n\n"
                            "2. The TalkType icon will appear in your top panel\n\n"
                            "3. Click the icon to:\n"
                            "   • Start/stop dictation service\n"
                            "   • Switch Whisper models\n"
                            "   • Access preferences"
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
                            text="Installation Failed"
                        )
                        error_dialog.format_secondary_text(
                            "Failed to install GNOME extension.\n\n"
                            "Please check your internet connection and try again."
                        )
                        error_dialog.run()
                        error_dialog.destroy()

                    return False

                GLib.idle_add(finish_install)

            # Start installation in background thread
            thread = threading.Thread(target=install_thread, daemon=True)
            thread.start()

    def _on_uninstall_extension_clicked(self, button):
        """Handle Uninstall Extension button click."""
        try:
            from . import extension_helper
        except ImportError:
            return

        # Show confirmation dialog
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Uninstall GNOME Extension?"
        )
        dialog.format_secondary_text(
            "This will remove the TalkType GNOME Shell extension.\n\n"
            "The main TalkType application will continue to work normally.\n\n"
            "Uninstall?"
        )

        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            success = extension_helper.uninstall_extension()

            if success:
                # Refresh extension status
                self._check_extension_status()

                # Show success message
                info = Gtk.MessageDialog(
                    transient_for=self.window,
                    flags=0,
                    message_type=Gtk.MessageType.INFO,
                    buttons=Gtk.ButtonsType.OK,
                    text="Extension Uninstalled"
                )
                info.format_secondary_text(
                    "The GNOME extension has been removed.\n\n"
                    "Restart GNOME Shell to complete:\n"
                    "  Press Alt+F2, type 'r', press Enter"
                )
                info.run()
                info.destroy()
            else:
                # Show error
                error = Gtk.MessageDialog(
                    transient_for=self.window,
                    flags=0,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Uninstall Failed"
                )
                error.format_secondary_text("Failed to uninstall the extension.")
                error.run()
                error.destroy()

    def _on_restart_info_clicked(self, button):
        """Show information about restarting GNOME Shell."""
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="How to Restart GNOME Shell"
        )
        dialog.format_secondary_markup(
            "<b>To activate or update the extension:</b>\n\n"
            "<b>Method 1: Quick Restart (Recommended)</b>\n"
            "1. Press <b>Alt+F2</b>\n"
            "2. Type <b>r</b> and press <b>Enter</b>\n"
            "3. GNOME Shell will restart immediately\n\n"
            "<b>Method 2: Log Out</b>\n"
            "1. Log out of your session\n"
            "2. Log back in\n\n"
            "⚠️  <b>Note:</b> Wayland sessions require Method 2"
        )
        dialog.run()
        dialog.destroy()

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
    
    def check_and_download_model(self, model_name):
        """Check if model exists, download with progress if needed.

        Returns:
            tuple: (success: bool, was_downloaded: bool)
        """
        import os

        # Check if model is already cached
        cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
        model_dir = f"models--Systran--faster-whisper-{model_name}"
        model_path = os.path.join(cache_dir, model_dir)

        if os.path.exists(model_path):
            print(f"Model {model_name} already cached")
            return (True, False)  # Success, but not downloaded

        # Model needs downloading - show progress dialog
        print(f"Model {model_name} not found, downloading...")

        dialog = Gtk.Dialog(title="Downloading Model")
        dialog.set_transient_for(self.window)
        dialog.set_modal(True)
        dialog.set_default_size(450, 180)
        dialog.set_resizable(False)

        content = dialog.get_content_area()
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_spacing(15)

        # Model sizes for display
        model_sizes = {
            "tiny": "39 MB",
            "base": "74 MB",
            "small": "244 MB",
            "medium": "769 MB",
            "large-v3": "~3 GB"
        }
        size_str = model_sizes.get(model_name, "unknown size")

        # Status label
        status_label = Gtk.Label()
        status_label.set_markup(f'<b>Downloading Whisper model: {model_name}</b>\n<span size="small">({size_str})</span>\n\nThis may take a few minutes depending on your connection...')
        status_label.set_line_wrap(True)
        content.pack_start(status_label, False, False, 0)

        # Progress bar with percentage
        progress_bar = Gtk.ProgressBar()
        progress_bar.set_show_text(True)
        progress_bar.set_text("0%")
        content.pack_start(progress_bar, False, False, 0)

        # Add Cancel button
        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.set_can_default(True)
        cancel_button.show()
        dialog.add_action_widget(cancel_button, Gtk.ResponseType.CANCEL)

        dialog.show_all()

        # Download in background thread with cancellation support
        import threading
        import os as prefs_os
        cancel_event = threading.Event()
        download_complete = {"done": False, "success": False, "cancelled": False}
        progress_state = {'last_percent': -1}

        # Model sizes in bytes for progress estimation (actual download sizes)
        model_sizes_bytes = {
            "tiny": 75 * 1024 * 1024,       # ~75 MB actual
            "base": 145 * 1024 * 1024,      # ~145 MB actual
            "small": 488 * 1024 * 1024,     # ~488 MB actual
            "medium": 1533 * 1024 * 1024,   # ~1.5 GB actual
            "large-v3": 3100 * 1024 * 1024, # ~3.1 GB actual
        }
        expected_size = model_sizes_bytes.get(model_name, 500 * 1024 * 1024)

        def get_cache_dir_size():
            """Get the size of HuggingFace cache for this model"""
            try:
                cache_base = prefs_os.path.expanduser("~/.cache/huggingface/hub")
                repo_folder = f"models--Systran--faster-whisper-{model_name}"
                cache_path = prefs_os.path.join(cache_base, repo_folder)

                if not prefs_os.path.exists(cache_path):
                    return 0

                total_size = 0
                for dirpath, dirnames, filenames in prefs_os.walk(cache_path):
                    for f in filenames:
                        fp = prefs_os.path.join(dirpath, f)
                        try:
                            total_size += prefs_os.path.getsize(fp)
                        except OSError:
                            pass
                return total_size
            except Exception:
                return 0

        def download_model():
            try:
                import warnings

                # Suppress PyTorch CUDA warnings BEFORE importing anything that imports torch
                warnings.filterwarnings('ignore', message='Could not load CUDA library.*')
                warnings.filterwarnings('ignore', category=UserWarning, module='torch')

                # Check for cancellation before starting
                if cancel_event.is_set():
                    download_complete["cancelled"] = True
                    return

                from faster_whisper import WhisperModel

                # This will download the model if needed
                WhisperModel(model_name, device="cpu", compute_type="int8")

                # Check for cancellation after download
                if cancel_event.is_set():
                    download_complete["cancelled"] = True
                else:
                    download_complete["success"] = True

            except Exception as e:
                print(f"Model download failed: {e}")
                download_complete["success"] = False
            finally:
                download_complete["done"] = True

        thread = threading.Thread(target=download_model)
        thread.daemon = True
        thread.start()

        # Update progress bar by monitoring cache directory size
        def update_progress():
            if download_complete["done"]:
                # Set to 100% before closing
                progress_bar.set_fraction(1.0)
                progress_bar.set_text("100%")
                GLib.timeout_add(200, lambda: dialog.response(Gtk.ResponseType.OK) or False)
                return False

            if cancel_event.is_set():
                return False

            current_size = get_cache_dir_size()
            percent = min(99, int((current_size / expected_size) * 100))

            if percent != progress_state['last_percent']:
                progress_state['last_percent'] = percent
                progress_bar.set_fraction(percent / 100.0)
                progress_bar.set_text(f"{percent}%")

            return True

        GLib.timeout_add(200, update_progress)

        # Wait for download (dialog.run() blocks until response)
        response = dialog.run()

        # Handle cancel button click
        if response == Gtk.ResponseType.CANCEL:
            cancel_event.set()
            download_complete["cancelled"] = True
            print(f"User cancelled {model_name} model download")

        dialog.destroy()

        # Show success message if download completed successfully
        if download_complete["success"]:
            print(f"✅ Model {model_name} downloaded successfully")

            # Show success dialog
            success_dialog = Gtk.MessageDialog(
                transient_for=self.window,
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="Model Downloaded Successfully!"
            )

            # Apply dark theme
            settings = Gtk.Settings.get_default()
            if settings:
                settings.set_property("gtk-application-prefer-dark-theme", True)

            success_dialog.format_secondary_text(f"The {model_name} model has been downloaded and is ready to use.")
            success_dialog.run()
            success_dialog.destroy()

        return (download_complete["success"], download_complete["success"])  # (success, was_downloaded)

    def restart_service(self):
        """Restart the dictation service."""
        try:
            import subprocess
            import time

            # Debug: print what config will be loaded
            print(f"📄 Config file: {CONFIG_PATH}")
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r") as f:
                    content = f.read()
                    # Extract model and device for debug
                    for line in content.split("\n"):
                        if line.startswith("model =") or line.startswith("device ="):
                            print(f"   {line}")
            else:
                print(f"   ⚠️  Config file does not exist!")

            # Kill existing talktype.app processes
            subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
            # Wait a moment for processes to terminate
            time.sleep(1)

            # Find the dictate script relative to this module (AppImage path)
            # __file__ is in usr/src/talktype/prefs.py
            # dictate is in usr/bin/dictate
            src_dir = os.path.dirname(__file__)  # usr/src/talktype
            usr_dir = os.path.dirname(os.path.dirname(src_dir))  # usr
            dictate_script = os.path.join(usr_dir, "bin", "dictate")

            if os.path.exists(dictate_script):
                # Use the dictate script which has proper paths set up (AppImage)
                subprocess.Popen([dictate_script], env=os.environ.copy())
                print(f"Restarted dictation service via {dictate_script}")
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
                    print(f"Dev mode detected - setting PYTHONPATH for service restart")

                subprocess.Popen([sys.executable, "-m", "talktype.app"], env=env)
                print("Restarted dictation service via Python module")
            return True
        except Exception as e:
            print(f"Failed to restart service: {e}")
            return False
    
    def on_tab_switched(self, notebook, page, page_num):
        """Scroll to top when switching tabs."""
        if hasattr(self, 'main_scrolled') and self.main_scrolled:
            # Get the vertical adjustment and scroll to top
            vadj = self.main_scrolled.get_vadjustment()
            if vadj:
                vadj.set_value(0)

    def on_apply(self, button):
        """Apply changes and restart service without closing."""
        # Save custom commands first
        if hasattr(self, 'commands_store'):
            self._save_custom_commands()
        
        if self.save_config():
            # Check if model needs downloading
            if hasattr(self, 'model_combo'):
                model_name = self.model_combo.get_active_text()
                if model_name:
                    success, was_downloaded = self.check_and_download_model(model_name)
                    if not success:
                        # Model download failed
                        dialog = Gtk.MessageDialog(
                            transient_for=self.window,
                            flags=0,
                            message_type=Gtk.MessageType.ERROR,
                            buttons=Gtk.ButtonsType.OK,
                            text="Model download failed!"
                        )

                        # Apply dark theme
                        settings = Gtk.Settings.get_default()
                        if settings:
                            settings.set_property("gtk-application-prefer-dark-theme", True)

                        dialog.format_secondary_text("Failed to download the Whisper model. Please check your internet connection.")
                        dialog.run()
                        dialog.destroy()
                        return

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

                # Apply dark theme
                settings = Gtk.Settings.get_default()
                if settings:
                    settings.set_property("gtk-application-prefer-dark-theme", True)

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
        # Save custom commands first
        if hasattr(self, 'commands_store'):
            self._save_custom_commands()
        
        if self.save_config():
            model_was_downloaded = False

            # Check if model needs downloading
            if hasattr(self, 'model_combo'):
                model_name = self.model_combo.get_active_text()
                if model_name:
                    success, was_downloaded = self.check_and_download_model(model_name)
                    model_was_downloaded = was_downloaded
                    if not success:
                        # Model download failed
                        dialog = Gtk.MessageDialog(
                            transient_for=self.window,
                            flags=0,
                            message_type=Gtk.MessageType.ERROR,
                            buttons=Gtk.ButtonsType.OK,
                            text="Model download failed!"
                        )

                        # Apply dark theme
                        settings = Gtk.Settings.get_default()
                        if settings:
                            settings.set_property("gtk-application-prefer-dark-theme", True)

                        dialog.format_secondary_text("Failed to download the Whisper model. Please check your internet connection.")
                        dialog.run()
                        dialog.destroy()
                        return

            # Restart the service
            service_restarted = self.restart_service()

            # If model was just downloaded, keep preferences open so user can adjust other settings
            if model_was_downloaded:
                # Don't close the window - let user make more changes if needed
                return

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

    def _on_test_hotkeys(self, button):
        """Show hotkey test dialog."""
        from evdev import ecodes

        # IMPORTANT: Stop the dictation service first!
        # The service grabs keys at the evdev level (kernel), which intercepts them
        # BEFORE GTK can see them. We must stop the service to test hotkeys properly.
        service_was_running = False
        dbus_iface = _get_dbus_interface()
        if dbus_iface:
            try:
                # Check if service is running by trying to get its status
                dbus_iface.StopService()
                service_was_running = True
                print("Stopped dictation service for hotkey testing")
            except Exception as e:
                print(f"Could not stop service (may not be running): {e}")

        dialog = Gtk.Dialog(title="Test Hotkeys", transient_for=self.window)
        dialog.set_default_size(450, 280)
        dialog.set_modal(True)
        dialog.set_position(Gtk.WindowPosition.CENTER)

        content = dialog.get_content_area()
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        content.set_margin_start(25)
        content.set_margin_end(25)
        content.set_spacing(15)

        # Instructions
        instructions = Gtk.Label()
        instructions.set_markup('<span size="large"><b>Test Your Hotkeys</b></span>\n\nPress each hotkey to verify it works:')
        instructions.set_xalign(0)
        content.pack_start(instructions, False, False, 0)

        # Get current mode and hotkeys
        mode = self.config.get("mode", "hold")
        hold_key = self.config.get("hotkey", "F8")
        toggle_key = self.config.get("toggle_hotkey", "F9")

        # Test status labels
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        status_box.set_margin_top(10)

        hold_label = Gtk.Label()
        hold_label.set_markup(f'<b>{hold_key}</b> (Push-to-talk): <span color="#999999">Not tested</span>')
        hold_label.set_xalign(0)
        status_box.pack_start(hold_label, False, False, 0)

        toggle_label = Gtk.Label()
        toggle_label.set_markup(f'<b>{toggle_key}</b> (Toggle mode): <span color="#999999">Not tested</span>')
        toggle_label.set_xalign(0)
        status_box.pack_start(toggle_label, False, False, 0)

        content.pack_start(status_box, False, False, 0)

        # Track tested keys
        tested_keys = {"hold": False, "toggle": False}

        # Key press event handler
        def on_key_press(widget, event):
            keyname = Gtk.accelerator_name(event.keyval, 0)

            if keyname == hold_key:
                tested_keys["hold"] = True
                hold_label.set_markup(f'<b>{hold_key}</b> (Push-to-talk): <span color="#4CAF50">✓ Working!</span>')
            elif keyname == toggle_key:
                tested_keys["toggle"] = True
                toggle_label.set_markup(f'<b>{toggle_key}</b> (Toggle mode): <span color="#4CAF50">✓ Working!</span>')

            return True  # Stop event propagation

        # Connect key press handler to dialog
        dialog.connect("key-press-event", on_key_press)

        # Info label
        info_label = Gtk.Label()
        info_label.set_markup('<i>The dictation service is paused while this dialog is open.\nClose this dialog to resume dictation.</i>')
        info_label.set_line_wrap(True)
        info_label.set_xalign(0)
        info_label.set_margin_top(10)
        content.pack_start(info_label, False, False, 0)

        # Close button
        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda w: dialog.destroy())
        dialog.add_action_widget(close_button, Gtk.ResponseType.CLOSE)

        dialog.show_all()
        dialog.run()
        dialog.destroy()

        # Restart the dictation service if it was running before
        if service_was_running and dbus_iface:
            try:
                dbus_iface.StartService()
                print("Restarted dictation service after hotkey testing")
            except Exception as e:
                print(f"Could not restart service: {e}")

    def on_help(self, button):
        """Show help dialog with TalkType features and instructions."""
        from .help_dialog import show_help_dialog
        show_help_dialog()



def main():
    import argparse
    parser = argparse.ArgumentParser(description="TalkType Preferences")
    parser.add_argument("--tab", choices=["general", "audio", "advanced", "commands", "updates"],
                        help="Tab to open initially")
    args = parser.parse_args()

    _acquire_prefs_singleton()
    app = PreferencesWindow()

    # Switch to specified tab if requested
    if args.tab:
        tab_indices = {
            "general": 0,
            "audio": 1,
            "advanced": 2,
            "commands": 3,
            "updates": 4
        }
        if args.tab in tab_indices:
            app.notebook.set_current_page(tab_indices[args.tab])

    Gtk.main()

if __name__ == "__main__":
    main()

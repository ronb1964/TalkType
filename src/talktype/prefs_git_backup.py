import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
import os
import subprocess
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

class PreferencesWindow:
    def __init__(self):
        self.window = Gtk.Window(title="Ron Dictation Preferences")
        self.window.set_default_size(500, 400)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        
        # Load current config
        self.config = self.load_config()
        
        # Create UI
        self.create_ui()
        
        # Show window
        self.window.show_all()
        
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
    
    def save_config(self):
        """Save config to TOML file."""
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                f.write("# Ron Dictation config\n")
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
        vbox.set_margin_left(20)
        vbox.set_margin_right(20)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>Ron Dictation Preferences</b></big>")
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
        cancel_btn.connect("clicked", lambda x: self.window.destroy())
        
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
        grid.set_margin_left(20)
        grid.set_margin_right(20)
        grid.set_margin_top(20)
        grid.set_margin_bottom(20)
        
        row = 0
        
        # Model selection
        grid.attach(Gtk.Label(label="Model:", xalign=0), 0, row, 1, 1)
        model_combo = Gtk.ComboBoxText()
        for model in ["tiny", "base", "small", "medium", "large-v3"]:
            model_combo.append_text(model)
        model_combo.set_active_id(self.config["model"])
        model_combo.connect("changed", lambda x: self.update_config("model", x.get_active_text()))
        grid.attach(model_combo, 1, row, 1, 1)
        row += 1
        
        # Device selection
        grid.attach(Gtk.Label(label="Device:", xalign=0), 0, row, 1, 1)
        device_combo = Gtk.ComboBoxText()
        device_combo.append("cpu", "CPU")
        device_combo.append("cuda", "CUDA (GPU)")
        device_combo.set_active_id(self.config["device"])
        device_combo.connect("changed", lambda x: self.update_config("device", x.get_active_id()))
        grid.attach(device_combo, 1, row, 1, 1)
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
        mode_combo.append("hold", "Hold to Talk")
        mode_combo.append("toggle", "Press to Toggle")
        mode_combo.set_active_id(self.config["mode"])
        mode_combo.connect("changed", lambda x: self.update_config("mode", x.get_active_id()))
        grid.attach(mode_combo, 1, row, 1, 1)
        row += 1
        
        # Hotkey
        grid.attach(Gtk.Label(label="Hold Hotkey:", xalign=0), 0, row, 1, 1)
        hotkey_entry = Gtk.Entry()
        hotkey_entry.set_text(self.config["hotkey"])
        hotkey_entry.connect("changed", lambda x: self.update_config("hotkey", x.get_text()))
        grid.attach(hotkey_entry, 1, row, 1, 1)
        row += 1
        
        # Toggle hotkey
        grid.attach(Gtk.Label(label="Toggle Hotkey:", xalign=0), 0, row, 1, 1)
        toggle_entry = Gtk.Entry()
        toggle_entry.set_text(self.config["toggle_hotkey"])
        toggle_entry.connect("changed", lambda x: self.update_config("toggle_hotkey", x.get_text()))
        grid.attach(toggle_entry, 1, row, 1, 1)
        row += 1
        
        return grid
    
    def create_audio_tab(self):
        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(10)
        grid.set_margin_left(20)
        grid.set_margin_right(20)
        grid.set_margin_top(20)
        grid.set_margin_bottom(20)
        
        row = 0
        
        # Microphone
        grid.attach(Gtk.Label(label="Microphone:", xalign=0), 0, row, 1, 1)
        mic_entry = Gtk.Entry()
        mic_entry.set_text(self.config["mic"])
        mic_entry.set_placeholder_text("Leave empty for default, or enter device name substring")
        mic_entry.connect("changed", lambda x: self.update_config("mic", x.get_text()))
        grid.attach(mic_entry, 1, row, 1, 1)
        row += 1
        
        # Beeps
        beeps_check = Gtk.CheckButton(label="Play beeps for start/stop/ready")
        beeps_check.set_active(self.config["beeps"])
        beeps_check.connect("toggled", lambda x: self.update_config("beeps", x.get_active()))
        grid.attach(beeps_check, 0, row, 2, 1)
        row += 1
        
        # Notifications
        notify_check = Gtk.CheckButton(label="Show desktop notifications")
        notify_check.set_active(self.config["notify"])
        notify_check.connect("toggled", lambda x: self.update_config("notify", x.get_active()))
        grid.attach(notify_check, 0, row, 2, 1)
        row += 1
        
        return grid
    
    def create_advanced_tab(self):
        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(10)
        grid.set_margin_left(20)
        grid.set_margin_right(20)
        grid.set_margin_top(20)
        grid.set_margin_bottom(20)
        
        row = 0
        
        # Smart quotes
        quotes_check = Gtk.CheckButton(label="Use smart quotes (" ")")
        quotes_check.set_active(self.config["smart_quotes"])
        quotes_check.connect("toggled", lambda x: self.update_config("smart_quotes", x.get_active()))
        grid.attach(quotes_check, 0, row, 2, 1)
        row += 1
        
        # Auto space
        space_check = Gtk.CheckButton(label="Auto-space between utterances")
        space_check.set_active(self.config["auto_space"])
        space_check.connect("toggled", lambda x: self.update_config("auto_space", x.get_active()))
        grid.attach(space_check, 0, row, 2, 1)
        row += 1
        
        # Auto period
        period_check = Gtk.CheckButton(label="Auto-add period at end of sentences")
        period_check.set_active(self.config["auto_period"])
        period_check.connect("toggled", lambda x: self.update_config("auto_period", x.get_active()))
        grid.attach(period_check, 0, row, 2, 1)
        row += 1
        
        # Injection mode
        grid.attach(Gtk.Label(label="Text Injection:", xalign=0), 0, row, 1, 1)
        inject_combo = Gtk.ComboBoxText()
        inject_combo.append("type", "Keystroke Typing")
        inject_combo.append("paste", "Clipboard Paste")
        inject_combo.set_active_id(self.config["injection_mode"])
        inject_combo.connect("changed", lambda x: self.update_config("injection_mode", x.get_active_id()))
        grid.attach(inject_combo, 1, row, 1, 1)
        row += 1
        
        return grid
    
    def update_config(self, key, value):
        """Update config value."""
        self.config[key] = value
    
    def on_apply(self, button):
        """Apply changes without closing."""
        if self.save_config():
            # Show confirmation
            dialog = Gtk.MessageDialog(
                transient_for=self.window,
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="Settings saved successfully!"
            )
            dialog.format_secondary_text("Restart the service for changes to take effect.")
            dialog.run()
            dialog.destroy()
        else:
            # Show error
            dialog = Gtk.MessageDialog(
                transient_for=self.window,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Failed to save settings!"
            )
            dialog.run()
            dialog.destroy()
    
    def on_ok(self, button):
        """Save and close."""
        if self.save_config():
            self.window.destroy()
        else:
            self.on_apply(button)  # Show error dialog

def main():
    app = PreferencesWindow()
    Gtk.main()

if __name__ == "__main__":
    main()

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
from gi.repository import Gtk, AppIndicator3, GLib
import subprocess
import time
import os
import sys
import atexit

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
    try:
        if os.path.exists(_TRAY_PIDFILE):
            try:
                with open(_TRAY_PIDFILE, "r") as f:
                    old = int(f.read().strip() or "0")
            except Exception:
                old = 0
            if _pid_running(old):
                print("Another tray instance is already running. Exiting.")
                sys.exit(0)
        with open(_TRAY_PIDFILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        print(f"Warning: could not write tray pidfile: {e}")
    def _cleanup():
        try:
            with open(_TRAY_PIDFILE, "r") as f:
                cur = int(f.read().strip() or "0")
            if cur == os.getpid():
                os.remove(_TRAY_PIDFILE)
        except Exception:
            pass
    atexit.register(_cleanup)

class DictationTray:
    def __init__(self):
        self.indicator = AppIndicator3.Indicator.new(
            "talktype",
            "microphone-sensitivity-muted",  # start with muted icon
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title("TalkType")  # Set the app name
        
        # Store menu items for dynamic updates
        self.start_item = None
        self.stop_item = None
        
        self.update_icon_status()
        self.indicator.set_menu(self.build_menu())
        
        # Check service status every 3 seconds and update menu
        GLib.timeout_add_seconds(3, self.update_status_and_menu)
        
    def is_service_running(self):
        """Check if the dictation service is active."""
        try:
            # Check for running talktype.app process
            result = subprocess.run(["pgrep", "-f", "talktype.app"], 
                                  capture_output=True, text=True)
            return result.returncode == 0 and result.stdout.strip()
        except Exception:
            return False
    
    def update_icon_status(self):
        """Update icon based on service status."""
        if self.is_service_running():
            # Try different icon names for active state
            self.indicator.set_icon_full("microphone-sensitivity-high", "TalkType: Active")
        else:
            # Use muted icon for stopped state
            self.indicator.set_icon_full("microphone-sensitivity-muted", "TalkType: Stopped")
        return True  # Continue the timer
    
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
                print(f"Started dictation service via {dictate_script}")
            else:
                # Fallback: use sys.executable (bundled Python)
                subprocess.Popen([sys.executable, "-m", "talktype.app"], 
                               env=os.environ.copy())
                print("Started dictation service via Python module")
        except Exception as e:
            print(f"Failed to start service: {e}")
            import traceback
            traceback.print_exc()
        GLib.timeout_add_seconds(1, self.update_status_and_menu_once)
    
    def stop_service(self, _):
        """Stop the dictation service directly."""
        try:
            subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
            print("Stopped dictation service")
        except Exception as e:
            print(f"Failed to stop service: {e}")
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
                print(f"Restarted dictation service via {dictate_script}")
            else:
                # Fallback: use sys.executable (bundled Python)
                subprocess.Popen([sys.executable, "-m", "talktype.app"], 
                               env=os.environ.copy())
                print("Restarted dictation service via Python module")
        except Exception as e:
            print(f"Failed to restart service: {e}")
            import traceback
            traceback.print_exc()
        GLib.timeout_add_seconds(2, self.update_status_and_menu_once)
    
    def update_status_and_menu(self):
        """Update icon and menu item visibility based on service status."""
        self.update_icon_status()
        self.update_menu_items()
        return True  # Continue the timer
    
    def update_status_and_menu_once(self):
        """Update icon and menu items once."""
        self.update_icon_status()
        self.update_menu_items()
        return False  # Don't repeat
    
    def update_menu_items(self):
        """Show/hide Start/Stop menu items based on service status."""
        if self.start_item and self.stop_item:
            is_running = self.is_service_running()
            self.start_item.set_visible(not is_running)
            self.stop_item.set_visible(is_running)
    
    def open_preferences(self, _):
        """Launch preferences window."""
        try:
            # Use direct Python path for more reliable execution
            import os
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            python_path = sys.executable
            subprocess.Popen([python_path, "-m", "src.talktype.prefs"], 
                           cwd=project_dir)
        except Exception as e:
            print(f"Failed to open preferences: {e}")
    
    def download_cuda(self, _):
        """Download CUDA libraries for GPU acceleration."""
        try:
            from . import cuda_helper
            print("Starting CUDA download...")
            success = cuda_helper.download_cuda_libraries()
            if success:
                print("✅ CUDA libraries downloaded successfully!")
            else:
                print("❌ CUDA download failed")
        except Exception as e:
            print(f"Error downloading CUDA: {e}")
    
    def show_help(self, _):
        """Show help dialog with TalkType features and instructions."""
        dialog = Gtk.Dialog(title="TalkType Help")
        dialog.set_default_size(600, 500)
        dialog.set_modal(True)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        
        content = dialog.get_content_area()
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        content.set_margin_start(20)
        content.set_margin_end(20)
        
        # Create scrolled window for content
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content.pack_start(scrolled, True, True, 0)
        
        # Main content box
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        scrolled.add(vbox)
        
        # Header
        header = Gtk.Label()
        header.set_markup('<span size="x-large"><b>🎙️ TalkType - AI-Powered Dictation</b></span>')
        header.set_margin_bottom(10)
        vbox.pack_start(header, False, False, 0)
        
        # Getting Started section
        getting_started = Gtk.Label()
        getting_started.set_markup('''<b>🚀 Getting Started:</b>
1. <b>Start the Service:</b> Right-click the tray icon → "Start Service"
2. <b>Choose Your Mode:</b> 
   • <b>F8:</b> Push-to-talk (hold to record, release to stop)
   • <b>F9:</b> Toggle mode (press once to start, press again to stop)
   • <b>Recording Indicator:</b> A red microphone icon appears during active dictation
3. <b>Configure Settings:</b> Right-click → "Preferences" to customize hotkeys, language, etc.''')
        getting_started.set_line_wrap(True)
        getting_started.set_xalign(0)
        vbox.pack_start(getting_started, False, False, 0)
        
        # Features section
        features = Gtk.Label()
        features.set_markup('''<b>✨ Key Features:</b>
• <b>Dual Hotkey Modes:</b> F8 (push-to-talk) or F9 (toggle) - customizable in Preferences
• <b>Smart Text Processing:</b> Auto-punctuation, smart quotes, auto-spacing, auto-periods
• <b>Language Support:</b> Auto-detect language or manually select from 50+ languages
• <b>GPU Acceleration:</b> CUDA support for 3-5x faster transcription (NVIDIA GPUs)
• <b>Flexible Text Input:</b> Keystroke simulation or clipboard paste modes
• <b>Audio Control:</b> Microphone selection, level monitoring, and audio testing
• <b>System Integration:</b> Launch at login, system tray integration, notification sounds''')
        features.set_line_wrap(True)
        features.set_xalign(0)
        vbox.pack_start(features, False, False, 0)
        
        # GPU section
        gpu_section = Gtk.Label()
        gpu_section.set_markup('''<b>🎮 GPU Acceleration:</b>
If you have an NVIDIA graphics card, TalkType can use GPU acceleration for much faster transcription.
• CUDA libraries (~1.2GB) will be downloaded automatically on first run
• You can enable/disable GPU mode in Preferences → General → Processing Device
• GPU mode is 3-5x faster than CPU mode''')
        gpu_section.set_line_wrap(True)
        gpu_section.set_xalign(0)
        vbox.pack_start(gpu_section, False, False, 0)
        
        # Power Management section
        power_section = Gtk.Label()
        power_section.set_markup('''<b>🔋 Power Management:</b>
TalkType includes an intelligent timeout feature to save system resources and battery life:
• <b>Auto-timeout:</b> Service automatically stops after a period of inactivity
• <b>Configurable:</b> Set timeout duration in Preferences → Advanced
• <b>Smart detection:</b> Resets timer when you use hotkeys or interact with the app
• <b>Battery friendly:</b> Reduces CPU/GPU usage when not actively dictating''')
        power_section.set_line_wrap(True)
        power_section.set_xalign(0)
        vbox.pack_start(power_section, False, False, 0)
        
        # Tips section
        tips = Gtk.Label()
        tips.set_markup('''<b>💡 Tips & Troubleshooting:</b>
• <b>Best Results:</b> Speak clearly and at a normal pace
• <b>Audio Setup:</b> Use the microphone test in Preferences to check audio levels
• <b>Status Indicators:</b> Tray icon shows service status (tooltip shows "running" or "stopped")
• <b>Troubleshooting:</b> Restart the service if transcription becomes unresponsive
• <b>Convenience:</b> Enable "Launch at Login" to start TalkType automatically
• <b>Hotkey Issues:</b> Check Preferences if hotkeys conflict with other applications''')
        tips.set_line_wrap(True)
        tips.set_xalign(0)
        vbox.pack_start(tips, False, False, 0)
        
        # Close button
        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda w: dialog.destroy())
        dialog.add_action_widget(close_button, Gtk.ResponseType.CLOSE)
        
        dialog.show_all()
        dialog.run()
        dialog.destroy()
    
    def quit_app(self, _):
        """Quit the tray and stop the dictation service."""
        try:
            # Stop the dictation service first
            subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
            print("Stopped dictation service")
        except Exception as e:
            print(f"Error stopping dictation service: {e}")
        # Then quit the tray
        Gtk.main_quit()
    
    def build_menu(self):
        menu = Gtk.Menu()
        
        # App title header (non-clickable)
        title_item = Gtk.MenuItem(label="🎙️ TalkType")
        title_item.set_sensitive(False)
        
        # Store references to start/stop items for dynamic visibility
        self.start_item = Gtk.MenuItem(label="Start Service")
        self.stop_item = Gtk.MenuItem(label="Stop Service")
        restart_item = Gtk.MenuItem(label="Restart Service")
        prefs_item = Gtk.MenuItem(label="Preferences...")
        help_item = Gtk.MenuItem(label="Help...")
        quit_item = Gtk.MenuItem(label="Quit Tray")
        
        self.start_item.connect("activate", self.start_service)
        self.stop_item.connect("activate", self.stop_service)
        restart_item.connect("activate", self.restart_service)
        prefs_item.connect("activate", self.open_preferences)
        help_item.connect("activate", self.show_help)
        quit_item.connect("activate", self.quit_app)
        
        # Check if we should show CUDA download option (fresh check each time)
        show_cuda_download = False
        try:
            import talktype.cuda_helper as cuda_helper
            # Only show CUDA download if GPU detected but CUDA not installed
            gpu_detected = cuda_helper.detect_nvidia_gpu()
            cuda_installed = cuda_helper.has_cuda_libraries()
            show_cuda_download = gpu_detected and not cuda_installed
            print(f"DEBUG: GPU detected: {gpu_detected}, CUDA installed: {cuda_installed}, Show download: {show_cuda_download}")
        except Exception as e:
            print(f"DEBUG: Error checking CUDA status: {e}")
        
        menu_items = [title_item, Gtk.SeparatorMenuItem(), self.start_item, self.stop_item, 
                     restart_item, Gtk.SeparatorMenuItem(), prefs_item]
        
        # Add CUDA download option if needed
        if show_cuda_download:
            cuda_item = Gtk.MenuItem(label="Download CUDA Libraries...")
            cuda_item.connect("activate", self.download_cuda)
            menu_items.append(cuda_item)
            print("DEBUG: Added CUDA download menu item")
        else:
            print("DEBUG: CUDA download menu item not added")
        
        menu_items.extend([help_item, quit_item])
        
        for item in menu_items:
            menu.append(item)
        menu.show_all()
        
        # Set initial menu state based on service status
        self.update_menu_items()
        
        return menu
    
    def refresh_menu(self):
        """Rebuild and refresh the tray menu (useful after CUDA installation)."""
        self.indicator.set_menu(self.build_menu())

def main():
    _acquire_tray_singleton()
    
    tray = DictationTray()
    
    # Check for first run and offer CUDA setup if applicable
    try:
        import talktype.cuda_helper as cuda_helper
        print(f"DEBUG: cuda_helper imported successfully")
        # Only show welcome dialog on first tray launch (not for prefs)
        if cuda_helper.is_first_run():
            print(f"DEBUG: First run detected, scheduling welcome dialog")
            # Schedule the welcome dialog after tray is initialized
            def show_welcome():
                print(f"DEBUG: Showing welcome dialog now")
                cuda_helper.offer_cuda_download(show_gui=True)
                print(f"DEBUG: Welcome dialog completed")
                # Refresh menu after CUDA installation (in case CUDA was installed)
                tray.refresh_menu()
                print(f"DEBUG: Menu refreshed")
                return False  # Don't repeat
            GLib.timeout_add(2000, show_welcome)  # Show after 2 seconds (increased delay)
        else:
            print(f"DEBUG: Not first run, skipping welcome dialog")
    except ImportError as e:
        print(f"DEBUG: Import error: {e}")
    except Exception as e:
        print(f"DEBUG: Error in welcome dialog setup: {e}")
    
    Gtk.main()

if __name__ == "__main__":
    main()

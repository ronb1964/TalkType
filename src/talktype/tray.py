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
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            subprocess.Popen([sys.executable, "-m", "src.talktype.app"], 
                           cwd=project_dir, 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
            print("Started dictation service")
        except Exception as e:
            print(f"Failed to start service: {e}")
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
            # Start again
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            subprocess.Popen([sys.executable, "-m", "src.talktype.app"], 
                           cwd=project_dir, 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
            print("Restarted dictation service")
        except Exception as e:
            print(f"Failed to restart service: {e}")
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
        quit_item = Gtk.MenuItem(label="Quit Tray")
        
        self.start_item.connect("activate", self.start_service)
        self.stop_item.connect("activate", self.stop_service)
        restart_item.connect("activate", self.restart_service)
        prefs_item.connect("activate", self.open_preferences)
        quit_item.connect("activate", self.quit_app)
        
        for item in (title_item, Gtk.SeparatorMenuItem(), self.start_item, self.stop_item, 
                     restart_item, Gtk.SeparatorMenuItem(), prefs_item, quit_item):
            menu.append(item)
        menu.show_all()
        
        # Set initial menu state based on service status
        self.update_menu_items()
        
        return menu

def main():
    _acquire_tray_singleton()
    tray = DictationTray()
    Gtk.main()

if __name__ == "__main__":
    main()

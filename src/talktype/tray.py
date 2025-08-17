import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
from gi.repository import Gtk, AppIndicator3, GLib
import subprocess
import time
import os
import sys
import atexit

SERVICE = "talktype.service"

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
        return ("dictate-tray" in cmd) or ("talktype.tray" in cmd)
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
        self.update_icon_status()
        self.indicator.set_menu(self.build_menu())
        
        # Check service status every 3 seconds
        GLib.timeout_add_seconds(3, self.update_icon_status)
        
    def is_service_running(self):
        """Check if the dictation service is active."""
        try:
            # Check for running Python processes with talktype.app
            result = subprocess.run(["pgrep", "-f", "talktype.app"], 
                                  capture_output=True, text=True)
            return result.returncode == 0
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
        """Start the dictation service."""
        try:
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            subprocess.Popen([sys.executable, "-m", "talktype.app"], cwd=project_dir)
            GLib.timeout_add_seconds(2, self.update_icon_status_once)
        except Exception as e:
            print(f"Failed to start service: {e}")
    
    def stop_service(self, _):
        """Stop the dictation service."""
        try:
            # Kill running app processes
            subprocess.run(["pkill", "-f", "talktype.app"])
            GLib.timeout_add_seconds(1, self.update_icon_status_once)
        except Exception as e:
            print(f"Failed to stop service: {e}")
    
    def restart_service(self, _):
        """Restart the dictation service."""
        try:
            # Stop first, then start
            subprocess.run(["pkill", "-f", "talktype.app"])
            GLib.timeout_add_seconds(1, lambda: self.start_service(None))
        except Exception as e:
            print(f"Failed to restart service: {e}")
    
    def update_icon_status_once(self):
        self.update_icon_status()
        return False  # Don't repeat
    
    def open_preferences(self, _):
        """Launch preferences window."""
        try:
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            subprocess.Popen([sys.executable, "-m", "talktype.prefs"], cwd=project_dir)
        except Exception as e:
            print(f"Failed to open preferences: {e}")
    
    def quit_app(self, _):
        Gtk.main_quit()
    
    def build_menu(self):
        menu = Gtk.Menu()
        
        # App title header (non-clickable)
        title_item = Gtk.MenuItem(label="🎙️ TalkType")
        title_item.set_sensitive(False)
        
        start_item = Gtk.MenuItem(label="Start Dictation")
        stop_item = Gtk.MenuItem(label="Stop Dictation")
        restart_item = Gtk.MenuItem(label="Restart Dictation")
        prefs_item = Gtk.MenuItem(label="Preferences...")
        quit_item = Gtk.MenuItem(label="Quit Tray")
        
        start_item.connect("activate", self.start_service)
        stop_item.connect("activate", self.stop_service)
        restart_item.connect("activate", self.restart_service)
        prefs_item.connect("activate", self.open_preferences)
        quit_item.connect("activate", self.quit_app)
        
        for item in (title_item, Gtk.SeparatorMenuItem(), start_item, stop_item, 
                     restart_item, Gtk.SeparatorMenuItem(), prefs_item, quit_item):
            menu.append(item)
        menu.show_all()
        return menu

def main():
    _acquire_tray_singleton()
    tray = DictationTray()
    Gtk.main()

if __name__ == "__main__":
    main()

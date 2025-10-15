import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
from gi.repository import Gtk, AppIndicator3, GLib
import subprocess
import time
import os
import sys
import atexit
import fcntl
from .logger import setup_logger

logger = setup_logger(__name__)

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
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title("TalkType")  # Set the app name

        # Store menu items for dynamic updates
        self.start_item = None
        self.stop_item = None

        self.update_icon_status()
        self.indicator.set_menu(self.build_menu())

        # Check service status every 3 seconds and update menu
        GLib.timeout_add_seconds(3, self.update_status_and_menu)

        # Auto-start will be triggered after welcome dialog on first run
        # or immediately if not first run (handled in main())
        
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
                # Fallback: use sys.executable (bundled Python)
                subprocess.Popen([sys.executable, "-m", "talktype.app"],
                               env=os.environ.copy())
                logger.info("Started dictation service via Python module")
        except Exception as e:
            print(f"Failed to start service: {e}")
            logger.error(f"Failed to start service: {e}", exc_info=True)
        GLib.timeout_add_seconds(1, self.update_status_and_menu_once)
    
    def stop_service(self, _):
        """Stop the dictation service directly."""
        try:
            subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
            logger.info("Stopped dictation service")
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
            logger.info("Starting CUDA download...")
            success = cuda_helper.download_cuda_libraries()
            if success:
                logger.info("CUDA libraries downloaded successfully")
            else:
                logger.error("CUDA download failed")
        except Exception as e:
            print(f"Error downloading CUDA: {e}")
            logger.error(f"Error downloading CUDA: {e}")
    
    def show_help(self, _):
        """Show help dialog with TalkType features and instructions."""
        dialog = Gtk.Dialog(title="TalkType Help")
        dialog.set_default_size(650, 550)
        dialog.set_modal(True)
        dialog.set_position(Gtk.WindowPosition.CENTER)

        content = dialog.get_content_area()
        content.set_margin_top(10)
        content.set_margin_bottom(10)
        content.set_margin_start(10)
        content.set_margin_end(10)

        # Create notebook (tabbed interface)
        notebook = Gtk.Notebook()
        notebook.set_tab_pos(Gtk.PositionType.TOP)
        content.pack_start(notebook, True, True, 0)

        # Helper function to create a tab with scrolled content
        def create_tab(title, markup_text):
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scrolled.set_margin_top(15)
            scrolled.set_margin_bottom(15)
            scrolled.set_margin_start(20)
            scrolled.set_margin_end(20)

            label = Gtk.Label()
            label.set_markup(markup_text)
            label.set_line_wrap(True)
            label.set_xalign(0)
            label.set_valign(Gtk.Align.START)

            scrolled.add(label)
            tab_label = Gtk.Label(label=title)
            notebook.append_page(scrolled, tab_label)

        # Tab 1: Getting Started
        create_tab("🚀 Getting Started", '''<span size="large"><b>Quick Start Guide</b></span>

<b>✨ TalkType is ready to use!</b>
The dictation service starts automatically when you launch TalkType.

<b>1. Begin Dictating</b>
Press <b>F8</b> (push-to-talk) or <b>F9</b> (toggle mode) to start
• <b>F8:</b> Hold to record, release to stop
• <b>F9:</b> Press once to start, press again to stop
• <b>Recording Indicator:</b> A red microphone icon appears during active dictation

<b>2. Configure Settings</b>
Right-click → "Preferences" to customize:
• Hotkeys (F8/F9 or custom keys)
• AI model (tiny to large-v3)
• Language (auto-detect or select manually)
• GPU acceleration (if you have NVIDIA GPU)
• Text input method (keyboard or clipboard)

<b>3. Dictate!</b>
Press your hotkey and speak clearly at a normal pace.
Text will be inserted where your cursor is located.

<b>💡 Auto-Timeout Feature:</b>
The service automatically pauses after 5 minutes of inactivity to save
system resources. Adjust this in Preferences → Advanced.

<b>Need more help?</b> Check the other tabs for detailed information.''')

        # Tab 2: Features
        create_tab("✨ Features", '''<span size="large"><b>Key Features</b></span>

<b>Dual Hotkey Modes</b>
• F8 (push-to-talk) or F9 (toggle) - fully customizable
• Visual recording indicator in system tray
• Audio beeps for start/stop feedback

<b>Smart Text Processing</b>
• Auto-punctuation for natural text flow
• Smart quotes (" " instead of " ")
• Auto-spacing before new text
• Optional auto-period at end of sentences

<b>Language Support</b>
• Auto-detect language from speech
• Manually select from 50+ supported languages
• Great for multilingual users

<b>Flexible Text Input</b>
• Keystroke simulation (ydotool/wtype)
• Clipboard paste mode (for apps with input issues)

<b>Audio Control</b>
• Microphone selection and testing
• Audio level monitoring
• Volume adjustment support

<b>System Integration</b>
• Launch at login option
• System tray integration
• Notification sounds (optional)
• Desktop notifications (optional)''')

        # Tab 3: AI Models
        create_tab("🤖 AI Models", '''<span size="large"><b>Choosing the Right AI Model</b></span>

Configure in: Preferences → General → Model

<b>Available Models:</b>

<b>• tiny (39 MB)</b>
  Speed: ⚡⚡⚡⚡⚡ Fastest
  Accuracy: ⭐⭐ Basic
  Best for: Quick notes, casual use

<b>• base (74 MB)</b>
  Speed: ⚡⚡⚡⚡ Fast
  Accuracy: ⭐⭐⭐ Good
  Best for: Casual dictation

<b>• small (244 MB)</b>
  Speed: ⚡⚡⚡ Balanced
  Accuracy: ⭐⭐⭐⭐ Very good
  Best for: General use (recommended)

<b>• medium (769 MB)</b>
  Speed: ⚡⚡ Slower
  Accuracy: ⭐⭐⭐⭐⭐ Excellent
  Best for: Professional dictation

<b>• large-v3 (~3 GB)</b>
  Speed: ⚡ Slowest
  Accuracy: ⭐⭐⭐⭐⭐⭐ Best possible
  Best for: Technical/professional work
  ⚠️ Takes 30-60 seconds to load initially, 10-20 seconds after

<b>Benefits of Larger Models:</b>
• Better recognition of uncommon words and technical terms
• More accurate with proper nouns and acronyms
• Improved punctuation and capitalization
• Better handling of accents and background noise
• Superior context awareness (e.g., "their" vs "there")
• More natural sentence structure

<b>Recommendation:</b>
Start with "small" for everyday use. Upgrade to "medium" or "large-v3"
if you need better accuracy for professional or technical dictation.''')

        # Tab 4: Advanced
        create_tab("⚙️ Advanced", '''<span size="large"><b>Advanced Features</b></span>

<b>🎮 GPU Acceleration</b>
If you have an NVIDIA graphics card, enable GPU acceleration for 3-5x faster transcription:
• On first run with NVIDIA GPU, you'll be offered to download CUDA libraries (~800MB)
• After download completes, click OK or Apply in Preferences to activate GPU mode
• Device automatically switches to "CUDA (GPU)" - no manual selection needed
• GPU mode significantly reduces transcription time (3-5x faster)
• Allows use of larger models without slowdown
• Can also download CUDA later: Preferences → Advanced → "Download CUDA Libraries"

<b>🔋 Power Management</b>
TalkType includes intelligent timeout to save system resources:
• <b>Auto-timeout:</b> Service stops automatically after inactivity
• <b>Configurable:</b> Set duration in Preferences → Advanced
• <b>Smart detection:</b> Timer resets when you use hotkeys
• <b>Battery friendly:</b> Reduces CPU/GPU usage when idle

Configure in: Preferences → Advanced Tab

<b>📝 Text Injection Modes</b>
Choose how text is inserted (Preferences → Advanced):
• <b>Keyboard Simulation (default):</b> Types text using ydotool/wtype
• <b>Clipboard Paste:</b> Copies to clipboard then simulates Ctrl+V
  Use this if keyboard simulation doesn't work in certain apps

<b>🎛️ Audio Settings</b>
Fine-tune audio in Preferences → Audio tab:
• Select specific microphone
• Test audio levels
• Adjust input volume (PulseAudio systems)
• Enable/disable audio beeps''')

        # Tab 5: Voice Commands
        create_tab("🗣️ Voice Commands", '''<span size="large"><b>Voice Commands Reference</b></span>

Use these spoken commands during dictation to insert punctuation and formatting.

<b>Punctuation:</b>
• Say <b>comma</b> for ,
• Say <b>period</b> or <b>full stop</b> for .
• Say <b>question mark</b> for ?
• Say <b>exclamation point</b> or <b>exclamation mark</b> for !
• Say <b>semicolon</b> for ;
• Say <b>colon</b> for :
• Say <b>apostrophe</b> for '
• Say <b>quote</b> for regular "
• Say <b>open quote</b> or <b>open quotes</b> for "
• Say <b>close quote</b> or <b>close quotes</b> for "
• Say <b>hyphen</b> or <b>dash</b> for -
• Say <b>em dash</b> for —
• Say <b>dot dot dot</b> or <b>ellipsis</b> for …

<b>Brackets &amp; Parentheses:</b>
• Say <b>open parenthesis</b> for (
• Say <b>close parenthesis</b> for )
• Say <b>open bracket</b> for [
• Say <b>close bracket</b> for ]
• Say <b>open brace</b> for {
• Say <b>close brace</b> for }

<b>Formatting:</b>
• Say <b>new line</b>, <b>newline</b>, <b>return</b>, or <b>line break</b> for a line break
• Say <b>new paragraph</b> or <b>paragraph break</b> for a double line break
• Say <b>tab</b> for a tab character (indent)
• Say <b>soft break</b> or <b>soft line</b> for three spaces

<b>Literal Words:</b>
To prevent conversion to punctuation, say:
• <b>literal period</b> → outputs the word "period" (not .)
• <b>the word period</b> → outputs the word "period" (not .)

<b>Usage Examples:</b>
Say: <i>Hello world comma how are you question mark</i>
Result: Hello world, how are you?

Say: <i>First sentence period new line Second sentence exclamation point</i>
Result: First sentence.
Second sentence!

Say: <i>The temperature is 98 point 6 degrees</i>
Result: The temperature is 98.6 degrees

Say: <i>Use the literal period command</i>
Result: Use the period command

<b>Smart Features:</b>
• Auto-capitalization after sentences
• Trailing commas converted to periods before line breaks
• Auto-period added if sentence has no punctuation
• Smart quote placement and spacing''')

        # Tab 6: Tips
        create_tab("💡 Tips", '''<span size="large"><b>Tips &amp; Troubleshooting</b></span>

<b>Getting Best Results:</b>
• Speak clearly at a normal pace
• Use a quality microphone for better accuracy
• Minimize background noise
• Pause briefly at sentence ends for better punctuation

<b>Audio Setup:</b>
• Use the microphone test in Preferences to check levels
• Adjust input volume if audio is too quiet or distorted
• Select the correct microphone if you have multiple inputs

<b>Status Indicators:</b>
• Tray icon tooltip shows running or stopped status
• Red microphone icon appears during recording
• Audio beeps indicate recording start/stop (can be disabled)

<b>Common Issues:</b>

<b>Hotkey not working:</b>
• Check if another app is using the same hotkey
• Try a different key in Preferences
• Ensure service is running

<b>Text not inserting:</b>
• Make sure cursor is in a text field
• Try clipboard paste mode (Preferences → Advanced)
• Check if the app has special input restrictions

<b>Transcription too slow:</b>
• Enable GPU acceleration if you have NVIDIA GPU
• Try a smaller AI model (tiny/base/small)
• Check if other programs are using GPU/CPU

<b>Service won't start:</b>
• Check logs: ~/.config/talktype/talktype.log
• Restart from tray menu: Stop Service then Start Service
• Ensure all dependencies are installed

<b>Convenience Features:</b>
• Enable Launch at Login to start automatically
• Use toggle mode (F9) for hands-free extended dictation
• Set auto-timeout to save battery when not in use''')

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

        # CUDA download option removed from tray menu - users can access it via Preferences
        menu_items = [title_item, Gtk.SeparatorMenuItem(), self.start_item, self.stop_item,
                     restart_item, Gtk.SeparatorMenuItem(), prefs_item, help_item, quit_item]
        
        for item in menu_items:
            menu.append(item)
        menu.show_all()
        
        # Set initial menu state based on service status
        self.update_menu_items()
        
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
    
    # Check for first run and offer CUDA setup if applicable
    try:
        import talktype.cuda_helper as cuda_helper
        # Only show welcome dialog on first tray launch (not for prefs)
        if cuda_helper.is_first_run():
            # Schedule the welcome dialog after tray is initialized
            def show_welcome():
                cuda_helper.offer_cuda_download(show_gui=True)
                # Refresh menu after CUDA installation (in case CUDA was installed)
                tray.refresh_menu()
                # NOW start the service (after welcome dialog)
                GLib.timeout_add(500, tray._auto_start_service)
                return False  # Don't repeat
            GLib.timeout_add(1500, show_welcome)  # Show after 1.5 seconds
        else:
            # Not first run, auto-start immediately
            GLib.timeout_add(1000, tray._auto_start_service)
    except Exception:
        # If any error, still try to auto-start
        GLib.timeout_add(1000, tray._auto_start_service)
    
    Gtk.main()

if __name__ == "__main__":
    main()

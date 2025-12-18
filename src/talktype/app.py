import os
# CRITICAL: Disable HuggingFace XET downloads BEFORE any imports
# XET bypasses tqdm_class progress tracking, breaking our download progress UI
os.environ["HF_HUB_DISABLE_XET"] = "1"

# Import torch_init FIRST to configure CUDA library paths before any torch imports
from .torch_init import init_cuda_for_pytorch
init_cuda_for_pytorch()

import sys, time, shutil, subprocess, tempfile, wave, atexit, argparse, fcntl
from dataclasses import dataclass
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from evdev import InputDevice, ecodes, list_devices

from .normalize import normalize_text
from .config import load_config, Settings, load_custom_commands
from .logger import setup_logger
from .recording_indicator import RecordingIndicator
import threading

logger = setup_logger(__name__)

# Optional desktop notifications via libnotify (gi)
_notify_ready = False
try:
    import gi
    gi.require_version("Notify", "0.7")
    from gi.repository import Notify
    Notify.init("TalkType")
    _notify_ready = True
except Exception:
    _notify_ready = False

def _notify(title: str, body: str):
    if not _notify_ready:
        return
    try:
        n = Notify.Notification.new(title, body)
        n.show()
    except Exception:
        pass

def show_hotkey_test_dialog(mode, hold_key, toggle_key):
    """Show modal dialog requiring user to test hotkeys before continuing."""
    try:
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, GLib

        dialog = Gtk.Dialog(title="Verify Your Hotkeys")
        dialog.set_default_size(520, 320)
        dialog.set_resizable(False)
        dialog.set_modal(True)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        dialog.set_keep_above(True)

        content = dialog.get_content_area()
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        content.set_margin_start(25)
        content.set_margin_end(25)
        content.set_spacing(15)

        # Header
        header = Gtk.Label()
        header.set_markup('<span size="large"><b>🎹 Verify Your Hotkeys</b></span>')
        content.pack_start(header, False, False, 0)

        # Instructions - always test both keys
        instructions = Gtk.Label()
        instructions.set_markup(
            '<b>Before you can start dictating, please test both hotkeys:</b>\n\n'
            f'1. Press <b>{hold_key}</b> (push-to-talk mode)\n'
            f'2. Press <b>{toggle_key}</b> (toggle mode)\n\n'
            'This ensures your hotkeys work and don\'t conflict with other apps.'
        )
        instructions.set_line_wrap(True)
        instructions.set_xalign(0)
        content.pack_start(instructions, False, False, 0)

        # Status labels
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        status_box.set_margin_top(10)

        hold_status = Gtk.Label()
        hold_status.set_markup(f'<b>{hold_key}</b>: <span color="#999999">⏳ Waiting...</span>')
        hold_status.set_xalign(0)
        status_box.pack_start(hold_status, False, False, 0)

        toggle_status = Gtk.Label()
        toggle_status.set_markup(f'<b>{toggle_key}</b>: <span color="#999999">⏳ Waiting...</span>')
        toggle_status.set_xalign(0)
        status_box.pack_start(toggle_status, False, False, 0)

        content.pack_start(status_box, False, False, 0)

        # Track tested keys
        tested = {"hold": False, "toggle": False}

        # Buttons (action area is managed automatically by dialog)
        change_keys_btn = Gtk.Button(label="Change Keys...")
        change_keys_btn.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.APPLY))
        change_keys_btn.set_tooltip_text("Open Preferences to change hotkeys")
        dialog.add_action_widget(change_keys_btn, Gtk.ResponseType.APPLY)

        skip_btn = Gtk.Button(label="Skip")
        skip_btn.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.CANCEL))
        skip_btn.set_tooltip_text("Skip verification (not recommended)")
        dialog.add_action_widget(skip_btn, Gtk.ResponseType.CANCEL)

        continue_btn = Gtk.Button(label="Continue")
        continue_btn.set_sensitive(False)  # Disabled until both keys tested
        continue_btn.get_style_context().add_class("suggested-action")
        continue_btn.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))
        dialog.add_action_widget(continue_btn, Gtk.ResponseType.OK)

        # Key press handler
        def on_key_press(widget, event):
            from gi.repository import Gdk
            keyname = Gdk.keyval_name(event.keyval)

            if keyname == hold_key and not tested["hold"]:
                tested["hold"] = True
                hold_status.set_markup(f'<b>{hold_key}</b>: <span color="#4CAF50">✓ Working!</span>')

                # Enable continue button when both keys tested
                if tested["hold"] and tested["toggle"]:
                    continue_btn.set_sensitive(True)
                    continue_btn.set_label("✓ Continue")

            elif keyname == toggle_key and not tested["toggle"]:
                tested["toggle"] = True
                toggle_status.set_markup(f'<b>{toggle_key}</b>: <span color="#4CAF50">✓ Working!</span>')

                # Enable continue button when both keys tested
                if tested["hold"] and tested["toggle"]:
                    continue_btn.set_sensitive(True)
                    continue_btn.set_label("✓ Continue")

            return True

        dialog.connect("key-press-event", on_key_press)

        # Dialog response handling
        result = {"action": None, "verified": False}

        def on_response(dialog, response_id):
            if response_id == Gtk.ResponseType.OK:
                result["action"] = "verified"
                result["verified"] = tested["hold"] and tested["toggle"]
            elif response_id == Gtk.ResponseType.APPLY:
                result["action"] = "change_keys"
            else:
                result["action"] = "skipped"
            dialog.destroy()
            Gtk.main_quit()

        dialog.connect("response", on_response)
        dialog.show_all()

        # Run a GTK main loop for this dialog
        Gtk.main()

        # Return results
        return (result["action"], result["verified"])

    except Exception as e:
        logger.error(f"Failed to show hotkey test dialog: {e}")
        return ("error", True)  # Fallback: allow continuation if dialog fails

def show_simple_hotkey_change_dialog(current_mode, current_hold_key, current_toggle_key):
    """Show a simple modal dialog to change hotkeys during first run."""
    try:
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk

        dialog = Gtk.Dialog(title="Change Your Hotkeys")
        dialog.set_default_size(500, 350)
        dialog.set_resizable(False)
        dialog.set_modal(True)
        dialog.set_position(Gtk.WindowPosition.CENTER)

        content = dialog.get_content_area()
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        content.set_margin_start(25)
        content.set_margin_end(25)
        content.set_spacing(15)

        # Header
        header = Gtk.Label()
        header.set_markup('<span size="large"><b>🎹 Choose Your Hotkeys</b></span>')
        content.pack_start(header, False, False, 0)

        # Instructions
        instructions = Gtk.Label()
        instructions.set_markup(
            'Select the hotkeys you want to use for dictation.\n'
            'Choose keys that won\'t conflict with other apps.'
        )
        instructions.set_line_wrap(True)
        content.pack_start(instructions, False, False, 0)

        # Mode selection
        mode_frame = Gtk.Frame(label="Activation Mode")
        mode_frame.set_margin_top(10)
        mode_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        mode_box.set_margin_top(10)
        mode_box.set_margin_bottom(10)
        mode_box.set_margin_start(15)
        mode_box.set_margin_end(15)

        hold_radio = Gtk.RadioButton(label="Push-to-Talk (Hold key to record)")
        toggle_radio = Gtk.RadioButton(label="Toggle (Press once to start, again to stop)", group=hold_radio)

        if current_mode == "toggle":
            toggle_radio.set_active(True)
        else:
            hold_radio.set_active(True)

        mode_box.pack_start(hold_radio, False, False, 0)
        mode_box.pack_start(toggle_radio, False, False, 0)
        mode_frame.add(mode_box)
        content.pack_start(mode_frame, False, False, 0)

        # Hotkey selection
        hotkey_frame = Gtk.Frame(label="Hotkeys")
        hotkey_frame.set_margin_top(10)
        hotkey_grid = Gtk.Grid()
        hotkey_grid.set_row_spacing(10)
        hotkey_grid.set_column_spacing(10)
        hotkey_grid.set_margin_top(10)
        hotkey_grid.set_margin_bottom(10)
        hotkey_grid.set_margin_start(15)
        hotkey_grid.set_margin_end(15)

        # Hold key
        hold_label = Gtk.Label(label="Push-to-Talk Key:")
        hold_label.set_xalign(0)
        hold_combo = Gtk.ComboBoxText()
        for key in ["F8", "F9", "F10", "F11", "F12", "F1", "F2", "F3", "F4", "F5", "F6", "F7"]:
            hold_combo.append_text(key)
        hold_combo.set_active_id(current_hold_key)
        if hold_combo.get_active() == -1:
            hold_combo.set_active(0)

        hotkey_grid.attach(hold_label, 0, 0, 1, 1)
        hotkey_grid.attach(hold_combo, 1, 0, 1, 1)

        # Toggle key
        toggle_label = Gtk.Label(label="Toggle Key:")
        toggle_label.set_xalign(0)
        toggle_combo = Gtk.ComboBoxText()
        for key in ["F8", "F9", "F10", "F11", "F12", "F1", "F2", "F3", "F4", "F5", "F6", "F7"]:
            toggle_combo.append_text(key)
        toggle_combo.set_active_id(current_toggle_key)
        if toggle_combo.get_active() == -1:
            toggle_combo.set_active(1)

        hotkey_grid.attach(toggle_label, 0, 1, 1, 1)
        hotkey_grid.attach(toggle_combo, 1, 1, 1, 1)

        hotkey_frame.add(hotkey_grid)
        content.pack_start(hotkey_frame, False, False, 0)

        # Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.set_margin_top(15)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.CANCEL))
        button_box.pack_start(cancel_btn, False, False, 0)

        save_btn = Gtk.Button(label="Save & Continue")
        save_btn.get_style_context().add_class("suggested-action")
        save_btn.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))
        button_box.pack_start(save_btn, False, False, 0)

        content.pack_start(button_box, False, False, 0)

        # Show dialog
        dialog.show_all()
        response = dialog.run()

        # Get values
        new_mode = "toggle" if toggle_radio.get_active() else "hold"
        new_hold_key = hold_combo.get_active_text()
        new_toggle_key = toggle_combo.get_active_text()

        dialog.destroy()

        if response == Gtk.ResponseType.OK:
            return (True, new_mode, new_hold_key, new_toggle_key)
        else:
            return (False, None, None, None)

    except Exception as e:
        logger.error(f"Failed to show hotkey change dialog: {e}")
        return (False, None, None, None)

# --- Single instance lock (user runtime dir) ---
def _runtime_dir():
    return os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

_PIDFILE = os.path.join(_runtime_dir(), "talktype.pid")

def _pid_running(pid: int) -> bool:
    if pid <= 0: return False
    proc = f"/proc/{pid}"
    if not os.path.exists(proc): return False
    try:
        with open(os.path.join(proc, "cmdline"), "rb") as f:
            cmd = f.read().decode(errors="ignore")
        return ("talktype.app" in cmd) or ("dictate" in cmd)
    except Exception:
        return True  # if in doubt, assume running

def _acquire_single_instance():
    """
    Acquire singleton lock using fcntl to prevent race conditions.
    Uses file locking which is atomic and prevents multiple instances.
    The lock is held for the lifetime of the process and auto-released on exit.
    """
    lockfile_path = os.path.join(_runtime_dir(), "talktype.lock")
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
        global _lockfile_handle
        _lockfile_handle = lockfile

        logger.debug(f"Acquired singleton lock: {lockfile_path}")

    except IOError:
        # Lock is already held by another process
        print("Another talktype instance is already running. Exiting.", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Warning: could not acquire singleton lock: {e}", file=sys.stderr)

# Global to keep lock file open
_lockfile_handle = None

# --- Runtime state ---
SAMPLE_RATE = 16000
CHANNELS = 1
MIN_HOLD_MS = 200
START_BEEP = (1200, 0.12)
CANCEL_BEEP = (500, 0.12)
READY_BEEP  = (1000, 0.09)

@dataclass
class RecordingState:
    """Encapsulates mutable state for recording sessions."""
    is_recording: bool = False
    was_cancelled: bool = False
    frames: list = None
    stream: object = None
    press_t0: float = None
    # Hotkey testing state
    hold_key_tested: bool = False
    toggle_key_tested: bool = False
    hotkey_test_start_time: float = None
    # Undo history - tracks last inserted text for voice-activated undo
    last_inserted_text: str = ""
    # Mid-sentence continuation - if True, lowercase the first letter of next dictation
    continue_mid_sentence: bool = False

    def __post_init__(self):
        if self.frames is None:
            self.frames = []

# Global recording state
state = RecordingState()

# Global recording indicator and D-Bus service (initialized in main)
recording_indicator = None
dbus_service = None

# Global typing delay (set from config in main)
_typing_delay = 12  # milliseconds, default value

# Global custom commands (loaded from config in main)
_custom_commands: dict[str, str] = {}

def _apply_custom_commands(text: str) -> str:
    """
    Apply user-defined custom voice commands to the transcribed text.
    
    Replaces spoken phrases with their configured replacements.
    Uses case-insensitive matching with word boundaries to avoid
    accidental replacements within longer words.
    
    Args:
        text: Raw transcribed text
        
    Returns:
        Text with custom commands applied
    """
    import re
    
    if not _custom_commands or not text:
        return text
    
    result = text
    
    # Sort by phrase length (longest first) to avoid partial matches
    sorted_commands = sorted(_custom_commands.items(), key=lambda x: len(x[0]), reverse=True)
    
    for phrase, replacement in sorted_commands:
        # Create a case-insensitive word boundary pattern
        # \b ensures we match whole words/phrases, not substrings
        pattern = r'\b' + re.escape(phrase) + r'\b'
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    if result != text:
        logger.info(f"Custom commands applied: {text!r} -> {result!r}")
    
    return result

def _beep(enabled: bool, freq=1000, duration=0.15):
    if not enabled:
        return
    samplerate = 44100
    t = np.linspace(0, duration, int(samplerate * duration), False)
    tone = (np.sin(freq * t * 2 * np.pi) * 0.2).astype(np.float32)
    try:
        sd.play(tone, samplerate); sd.wait()
    except Exception:
        pass

def _sd_callback(indata, frames_count, time_info, status):
    if state.is_recording:
        state.frames.append(indata.tobytes())

        # Update recording indicator with audio level
        if recording_indicator:
            # Calculate RMS (root mean square) for audio level
            audio_data = np.frombuffer(indata, dtype=np.int16)
            # Use float64 to avoid overflow in squaring
            audio_float = audio_data.astype(np.float64)
            rms = np.sqrt(np.mean(audio_float**2))
            # Normalize to 0-1 range (adjust multiplier for sensitivity)
            normalized = min(1.0, rms / 3000.0)
            recording_indicator.set_audio_level(normalized)

def _keycode_from_name(name: str) -> int | None:
    """Convert key name to evdev keycode. Returns None if name is empty (no hotkey configured)."""
    if not name or not name.strip():
        return None  # No hotkey configured - don't activate any key
    n = name.strip().upper()
    fkeys = {f"F{i}": getattr(ecodes, f"KEY_F{i}") for i in range(1,13)}
    if n in fkeys: return fkeys[n]
    if len(n) == 1 and "A" <= n <= "Z":
        return getattr(ecodes, f"KEY_{n}")
    return None  # Unknown key name - don't activate

def _pick_input_device(mic_substring: str | None):
    """Return device index or None for default."""
    try:
        q = sd.query_devices()
    except Exception:
        return None
    if not mic_substring:
        return None
    m = mic_substring.lower()
    candidates = [ (i,d) for i,d in enumerate(q) if d.get("max_input_channels",0) > 0 and m in d.get("name","").lower() ]
    if candidates:
        return candidates[0][0]
    return None

def start_recording(beeps_on: bool, notify_on: bool, input_device_idx):
    state.frames = []
    state.was_cancelled = False
    state.is_recording = True
    state.press_t0 = time.time()
    sd.default.channels = CHANNELS
    sd.default.samplerate = SAMPLE_RATE
    state.stream = sd.InputStream(callback=_sd_callback, dtype='int16', device=input_device_idx)
    state.stream.start()
    print("🎙️  Recording…")
    logger.debug("Recording started")
    _beep(beeps_on, *START_BEEP)
    if notify_on: _notify("TalkType", "Recording… (speak now)")

    # Show recording indicator
    if recording_indicator:
        try:
            recording_indicator.show_at_position()
            recording_indicator.start_recording()
        except Exception as e:
            print(f"⚠️  Failed to show recording indicator: {e}")
            logger.error(f"Failed to show recording indicator: {e}", exc_info=True)

def _stop_stream_safely():
    if state.stream:
        try:
            state.stream.stop(); state.stream.close()
        except Exception:
            pass
        state.stream = None

def cancel_recording(beeps_on: bool, notify_on: bool, reason="Cancelled"):
    state.is_recording = False
    state.was_cancelled = True
    _stop_stream_safely()
    _beep(beeps_on, *CANCEL_BEEP)
    print(f"⏸️  {reason}")
    logger.debug(f"Recording cancelled: {reason}")
    if notify_on: _notify("TalkType", reason)

    # Hide recording indicator
    if recording_indicator:
        recording_indicator.hide_indicator()

def _send_shift_enter():
    """Send Shift+Enter keystrokes to create line break without submitting."""
    if shutil.which("ydotool"):
        try:
            env = os.environ.copy()
            runtime = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            env.setdefault("YDOTOOL_SOCKET", os.path.join(runtime, ".ydotool_socket"))
            # KEY_LEFTSHIFT (42), KEY_ENTER (28)
            subprocess.run(["ydotool", "key", "42:1", "28:1", "28:0", "42:0"], check=False, env=env)
            return True
        except Exception as e:
            logger.debug(f"ydotool shift+enter failed: {e}")
    return False

def _send_enter():
    """Send Enter keystroke to create a new line."""
    if shutil.which("ydotool"):
        try:
            env = os.environ.copy()
            runtime = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            env.setdefault("YDOTOOL_SOCKET", os.path.join(runtime, ".ydotool_socket"))
            # KEY_ENTER (28)
            subprocess.run(["ydotool", "key", "28:1", "28:0"], check=False, env=env)
            return True
        except Exception as e:
            logger.debug(f"ydotool enter failed: {e}")
    return False

def _type_text(text: str):
    # Handle special markers first
    if "§SHIFT_ENTER§" in text:
        parts = text.split("§SHIFT_ENTER§")
        for i, part in enumerate(parts):
            if part:  # Type the text part
                _type_text_raw(part)
            if i < len(parts) - 1:  # Not the last part, send Shift+Enter
                time.sleep(0.05)  # Small delay between text and key
                _send_shift_enter()
                time.sleep(0.05)  # Small delay after key
        return
    
    # Handle regular newlines by converting them to Enter key presses
    if "\n" in text:
        parts = text.split("\n")
        for i, part in enumerate(parts):
            if part:  # Type the text part
                _type_text_raw(part)
            if i < len(parts) - 1:  # Not the last part, send Enter
                time.sleep(0.05)  # Small delay between text and key
                _send_enter()
                time.sleep(0.05)  # Small delay after key
        return
    
    # Normal text typing
    _type_text_raw(text)

def _type_text_raw(text: str):
    """
    Type text using ydotool or fallback methods.
    
    Uses global _typing_delay for keystroke timing.
    Higher values are slower but more reliable.
    Lower values may cause transposed letters.
    """
    global _typing_delay
    
    if shutil.which("ydotool"):
        try:
            env = os.environ.copy()
            runtime = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            socket_path = os.path.join(runtime, ".ydotool_socket")
            env.setdefault("YDOTOOL_SOCKET", socket_path)
            # -d = delay between keydown and keyup (ms)
            # -H = hold time before next key (ms)
            # Lower values are faster but may cause letters to arrive out of order
            delay_str = str(max(5, min(50, _typing_delay)))  # Clamp to 5-50ms
            logger.info(f"ydotool type: delay={delay_str}ms, socket={socket_path}, text_len={len(text)}")
            proc = subprocess.Popen(
                ["ydotool", "type", "-d", delay_str, "-H", delay_str, "-f", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env
            )
            stdout, stderr = proc.communicate(input=text.encode("utf-8"), timeout=20)
            if proc.returncode != 0:
                logger.error(f"ydotool type failed: rc={proc.returncode}, stderr={stderr.decode()}")
            else:
                logger.info(f"ydotool type succeeded: rc=0, typed {len(text)} chars")
            return
        except Exception as e:
            logger.debug(f"ydotool failed: {e}")
    if shutil.which("wtype"):
        subprocess.run(["wtype", "--", text], check=False); return
    if shutil.which("wl-copy"):
        try:
            import pyperclip
            pyperclip.copy(text)
            print("📋 Copied to clipboard. Ctrl+V to paste.")
            logger.info("Text copied to clipboard (fallback mode)")
            return
        except Exception:
            pass
    logger.error("Could not type text: no ydotool/wtype/wl-copy available")
    print("⚠️  Could not type text (no ydotool/wtype).")

def _paste_text(text: str, send_trailing_keys: bool = False):
    """
    Wayland paste injection: put text on clipboard, then Ctrl+V or Shift+Ctrl+V.
    
    Automatically detects terminal applications and uses Shift+Ctrl+V for them,
    regular Ctrl+V for everything else.

    Args:
        text: Text to paste (should NOT contain §SHIFT_ENTER§ markers)
        send_trailing_keys: If True, send additional key presses after paste
    """
    try:
        if shutil.which("wl-copy") and shutil.which("ydotool"):
            # Always use Ctrl+Shift+V for paste - works in both terminals and regular apps
            # This avoids complex and unreliable terminal detection
            # (Ctrl+Shift+V works universally on Wayland/GNOME)
            
            # Copy text to clipboard
            # wl-copy needs to stay running to serve clipboard requests
            import subprocess as _sp
            paste_start = time.time()
            print(f"⏱️  PASTE: Starting paste operation for {len(text)} chars")
            logger.info(f"TIMING: Starting paste operation for {len(text)} chars")
            proc = _sp.Popen(["wl-copy"], stdin=_sp.PIPE, stdout=_sp.PIPE, stderr=_sp.PIPE)
            proc.stdin.write(text.encode("utf-8"))
            proc.stdin.close()
            wl_copy_time = time.time() - paste_start
            print(f"⏱️  PASTE: wl-copy started in {wl_copy_time:.3f}s")
            logger.info(f"TIMING: wl-copy started in {wl_copy_time:.3f}s")

            # Wait for clipboard to be ready (needs time for wl-copy to set up)
            print(f"⏱️  PASTE: Waiting 0.08s for clipboard...")
            time.sleep(0.08)
            after_wait_time = time.time() - paste_start
            print(f"⏱️  PASTE: After clipboard wait: {after_wait_time:.3f}s")
            logger.info(f"TIMING: After clipboard wait: {after_wait_time:.3f}s")

            # Send Ctrl+Shift+V to paste - works universally in terminals and regular apps
            # KEY_LEFTSHIFT (42), KEY_LEFTCTRL (29), KEY_V (47)
            env = os.environ.copy()
            runtime = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            env.setdefault("YDOTOOL_SOCKET", os.path.join(runtime, ".ydotool_socket"))

            ydotool_start = time.time()
            # Always use Ctrl+Shift+V - works for both terminals and regular apps
            logger.debug("Using Ctrl+Shift+V for paste (universal)")
            # KEY_LEFTSHIFT=42, KEY_LEFTCTRL=29, KEY_V=47
            # Format: keycode:1 (down) or keycode:0 (up)
            _sp.run(["ydotool", "key",
                    "42:1", "29:1", "47:1", "47:0", "29:0", "42:0"],
                   check=False, env=env)
            ydotool_time = time.time() - ydotool_start
            print(f"⏱️  PASTE: ydotool command took {ydotool_time:.3f}s")
            logger.info(f"TIMING: ydotool paste command took {ydotool_time:.3f}s")
            
            # Brief delay for paste to register, then terminate wl-copy
            print(f"⏱️  PASTE: Waiting 0.05s for paste to register...")
            time.sleep(0.05)
            total_paste_time = time.time() - paste_start
            print(f"⏱️  PASTE: Total paste operation: {total_paste_time:.3f}s")
            logger.info(f"TIMING: Total paste operation time: {total_paste_time:.3f}s")
            try:
                proc.terminate()
                proc.wait(timeout=0.3)
            except:
                pass

            return True
    except subprocess.TimeoutExpired as e:
        logger.error(f"Paste injection timeout: {e}")
    except Exception as e:
        logger.error(f"Paste injection failed: {e}")
        pass
    return False

def _press_space():
    # Inject a literal Space keypress via ydotool when possible; fallback to typing a space
    if shutil.which("ydotool"):
        try:
            env = os.environ.copy()
            runtime = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            env.setdefault("YDOTOOL_SOCKET", os.path.join(runtime, ".ydotool_socket"))
            subprocess.run(["ydotool", "key", "57:1", "57:0"], check=False, env=env)
            return
        except Exception:
            pass
    if shutil.which("wtype"):
        subprocess.run(["wtype", "--", " "], check=False); return

def _determine_injection_method(injection_mode: str) -> tuple[str, str, str]:
    """
    Determine the best injection method based on mode and context.

    Args:
        injection_mode: User's configured mode ("type", "paste", or "auto")

    Returns:
        Tuple of (actual_mode, use_atspi, reason)
        - actual_mode: "type" or "paste" (what to actually use)
        - use_atspi: bool (whether to try AT-SPI first)
        - reason: str (explanation for logging)

    Note: This function is optimized for speed. Since we use Ctrl+Shift+V for paste
    (which works universally in terminals and regular apps), we default to paste
    mode and skip slow AT-SPI detection.
    """
    # If not auto mode, use user's choice directly
    if injection_mode.lower() != "auto":
        if injection_mode.lower() == "paste":
            return ("paste", False, "User selected paste mode")
        else:
            return ("type", False, "User selected type mode")

    # Auto mode: fast detection without AT-SPI (which can hang for 15+ seconds)
    # Since Ctrl+Shift+V works universally, paste is almost always the right choice

    # Quick process-based detection for common apps
    try:
        import subprocess
        # Single fast pgrep call to detect common terminal/editor processes
        result = subprocess.run(
            ["pgrep", "-a", "-u", str(os.getuid())],
            capture_output=True,
            text=True,
            timeout=0.3
        )
        if result.returncode == 0:
            procs = result.stdout.lower()
            # Check for terminals (all use paste with Ctrl+Shift+V)
            terminals = ["gnome-terminal", "konsole", "xterm", "kitty", "alacritty",
                        "terminator", "tilix", "ptyxis", "foot", "wezterm"]
            for term in terminals:
                if term in procs:
                    return ("paste", False, f"Auto: terminal ({term}), using paste")

            # Check for code editors (all work well with paste)
            editors = ["cursor", "/code", "sublime", "atom", "gedit", "kate", "neovim", "nvim"]
            for editor in editors:
                if editor in procs:
                    return ("paste", False, f"Auto: code editor detected, using paste")
    except subprocess.TimeoutExpired:
        logger.debug("Process detection timed out")
    except Exception as e:
        logger.debug(f"Process detection failed: {e}")

    # Default: use paste (Ctrl+Shift+V works universally)
    return ("paste", False, "Auto: defaulting to paste")

def _send_backspaces(count: int):
    """Send multiple backspace keypresses to delete characters."""
    if count <= 0:
        return
    if shutil.which("ydotool"):
        try:
            env = os.environ.copy()
            runtime = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            env.setdefault("YDOTOOL_SOCKET", os.path.join(runtime, ".ydotool_socket"))
            # KEY_BACKSPACE = 14
            # Build key sequence: press and release backspace 'count' times
            key_sequence = []
            for _ in range(count):
                key_sequence.extend(["14:1", "14:0"])
            subprocess.run(["ydotool", "key"] + key_sequence, check=False, env=env)
            return True
        except Exception as e:
            logger.debug(f"ydotool backspace failed: {e}")
    return False

def _detect_undo_command(raw_text: str) -> str | None:
    """
    Check if the raw transcription is an undo command.
    
    Returns the undo type ('word', 'sentence', 'paragraph') or None if not an undo command.
    Uses case-insensitive matching and handles common Whisper transcription variations.
    """
    # Normalize: lowercase, strip punctuation and extra whitespace
    import re
    normalized = re.sub(r'[^\w\s]', '', raw_text.lower()).strip()
    normalized = ' '.join(normalized.split())  # Collapse whitespace
    
    # Match undo commands - be flexible with variations Whisper might produce
    undo_patterns = {
        'word': ['undo last word', 'undo the last word', 'delete last word', 'remove last word'],
        'sentence': ['undo last sentence', 'undo the last sentence', 'delete last sentence', 'remove last sentence'],
        'paragraph': ['undo last paragraph', 'undo the last paragraph', 'delete last paragraph', 'remove last paragraph'],
        'everything': ['undo everything', 'undo all', 'delete everything', 'delete all', 'clear everything', 'clear all'],
    }
    
    for undo_type, patterns in undo_patterns.items():
        for pattern in patterns:
            if normalized == pattern:
                return undo_type
    
    return None

def _calculate_undo_length(text: str, undo_type: str) -> int:
    """
    Calculate how many characters to delete based on undo type.

    Args:
        text: The last inserted text
        undo_type: 'word', 'sentence', 'paragraph', or 'everything'

    Returns:
        Number of characters to delete (backspaces to send)
    """
    if not text:
        return 0

    # For 'everything', delete all tracked text
    if undo_type == 'everything':
        return len(text)
    
    # Remove trailing space if present (we add auto-space after dictation)
    text_to_analyze = text.rstrip()
    trailing_space = len(text) - len(text_to_analyze)
    
    if undo_type == 'word':
        # Find last word boundary (whitespace)
        # Delete from end back to last whitespace
        stripped = text_to_analyze.rstrip()
        last_space = stripped.rfind(' ')
        if last_space == -1:
            # No space found - delete everything
            return len(text)
        else:
            # Delete from after the last space to end (including trailing space)
            return len(text) - last_space - 1
    
    elif undo_type == 'sentence':
        # Find last sentence boundary (. ? ! …)
        # Work backwards from the end, skip any trailing punctuation
        import re
        # Remove trailing punctuation to find the previous sentence end
        text_stripped = text_to_analyze.rstrip('.?!… ')
        # Find the last sentence-ending punctuation
        match = re.search(r'[.?!…]\s*', text_stripped[::-1])
        if match:
            # Found a previous sentence end
            pos = len(text_stripped) - match.start()
            return len(text) - pos
        else:
            # No previous sentence found - delete everything
            return len(text)
    
    elif undo_type == 'paragraph':
        # Find last paragraph boundary (newlines or §SHIFT_ENTER§ markers)
        # First check for §SHIFT_ENTER§ marker
        marker = "§SHIFT_ENTER§"
        marker_pos = text_to_analyze.rfind(marker)
        newline_pos = text_to_analyze.rfind('\n')
        
        # Use whichever is later (closer to end)
        if marker_pos > newline_pos:
            # Delete from after the marker to end
            return len(text) - marker_pos - len(marker)
        elif newline_pos != -1:
            # Delete from after the newline to end
            return len(text) - newline_pos - 1
        else:
            # No paragraph break found - delete everything
            return len(text)
    
    return 0

def stop_recording(
    beeps_on: bool,
    smart_quotes: bool,
    notify_on: bool,
    language: str | None = None,
    auto_space: bool = True,
    auto_period: bool = True,
    injection_mode: str = "type",
):
    held_ms = int((time.time() - (state.press_t0 or time.time())) * 1000)
    if held_ms < MIN_HOLD_MS:
        cancel_recording(beeps_on, notify_on, f"Cancelled (held {held_ms} ms)"); return
    state.is_recording = False
    _stop_stream_safely()
    if state.was_cancelled: return

    # Hide recording indicator immediately when recording stops
    # This prevents it from interfering with text injection
    if recording_indicator:
        recording_indicator.hide_indicator()

    print("🛑 Recording stopped. Transcribing…")
    stop_recording_start = time.time()
    print(f"⏱️  TIMING: Stop recording at {stop_recording_start:.3f}")
    logger.info("=" * 60)
    logger.info("TIMING: Recording stopped, starting transcription")
    logger.debug("Recording stopped, starting transcription")
    # Convert captured bytes -> float32 mono PCM in [-1, 1]
    try:
        pcm_int16 = np.frombuffer(b''.join(state.frames), dtype=np.int16)
        if pcm_int16.size == 0:
            print("ℹ️  (No audio captured)")
            logger.debug("No audio captured during recording")
            return
        audio_f32 = (pcm_int16.astype(np.float32) / 32768.0)

        # Time the transcription to identify delays
        transcribe_start = time.time()
        segments, _ = model.transcribe(
                audio_f32,
                vad_filter=True,
                beam_size=1,
                condition_on_previous_text=False,
                temperature=0.0,
                without_timestamps=True,
                language=(language or None),
            )
        transcribe_time = time.time() - transcribe_start
        print(f"⏱️  TIMING: Transcription took {transcribe_time:.2f}s")
        logger.info(f"TIMING: Transcription completed in {transcribe_time:.2f}s")
        if transcribe_time > 2.0:  # Log if transcription takes more than 2 seconds
            logger.warning(f"⚠️  Transcription took {transcribe_time:.2f}s (first run may be slower due to CUDA compilation)")
        
        raw = " ".join(seg.text for seg in segments).strip()
        print(f"📝 Raw: {raw!r}")
        logger.info(f"Raw transcription: {raw!r}")
        
        post_transcribe_time = time.time() - stop_recording_start
        print(f"⏱️  TIMING: Total time to transcription: {post_transcribe_time:.2f}s")
        logger.info(f"TIMING: Time from stop_recording to transcription complete: {post_transcribe_time:.2f}s")
        
        # Check for undo commands before normalizing
        undo_type = _detect_undo_command(raw)
        if undo_type:
            logger.info(f"Undo command detected: {undo_type}")
            print(f"🔙 Undo command: {undo_type}")
            
            if not state.last_inserted_text:
                print("ℹ️  Nothing to undo (no previous dictation)")
                logger.info("Undo requested but no previous text to undo")
                _beep(beeps_on, *CANCEL_BEEP)
                if notify_on: _notify("TalkType", "Nothing to undo")
                return
            
            # Calculate how many characters to delete
            delete_count = _calculate_undo_length(state.last_inserted_text, undo_type)
            logger.info(f"Undo: deleting {delete_count} characters (last text was {len(state.last_inserted_text)} chars)")
            print(f"🔙 Undoing {delete_count} characters ({undo_type})")
            
            if delete_count > 0:
                _send_backspaces(delete_count)
                # Update the last_inserted_text to reflect what remains
                if delete_count >= len(state.last_inserted_text):
                    state.last_inserted_text = ""
                    state.continue_mid_sentence = False  # Starting fresh
                else:
                    state.last_inserted_text = state.last_inserted_text[:-delete_count]
                    # Check if we're mid-sentence (remaining text doesn't end with sentence punctuation)
                    remaining = state.last_inserted_text.rstrip()
                    if remaining and not remaining.endswith(('.', '?', '!', '…')):
                        state.continue_mid_sentence = True
                        logger.info("Mid-sentence continuation enabled for next dictation")
                    else:
                        state.continue_mid_sentence = False
                
                _beep(beeps_on, *READY_BEEP)
                if notify_on: _notify("TalkType", f"Undid last {undo_type}")
            else:
                print("ℹ️  Nothing to undo for this scope")
                _beep(beeps_on, *CANCEL_BEEP)
            
            return  # Don't inject the undo command as text
        
        # Apply custom voice commands (phrase → replacement)
        processed_raw = _apply_custom_commands(raw)
        
        text = normalize_text(processed_raw if smart_quotes else processed_raw.replace(""","\"").replace(""","\""))

        # Handle mid-sentence continuation after undo
        # Lowercase the first letter if we're continuing a sentence
        if state.continue_mid_sentence and text:
            # Only lowercase if the first character is uppercase
            if text[0].isupper():
                text = text[0].lower() + text[1:]
                logger.info(f"Lowercased first letter for mid-sentence continuation")
            state.continue_mid_sentence = False  # Reset the flag

        # Simple spacing: always add period+space or just space when auto features are on
        # Don't add auto-period or auto-space if text contains paragraph/line break markers
        # Also skip if text is ONLY markers (no actual content)
        has_break_markers = "§SHIFT_ENTER§" in text
        text_without_markers = text.replace("§SHIFT_ENTER§", "").strip()
        is_only_markers = has_break_markers and not text_without_markers

        if auto_period and text and not is_only_markers and not text.rstrip().endswith((".","?","!","…")):
            text = text.rstrip() + "."
        if auto_space and text and not is_only_markers and not text.endswith((" ", "\n", "\t")):
            text = text + " "
        logger.info(f"Normalized text: {text!r}")

        # Beep immediately after transcription completes (user feedback)
        pre_beep_time = time.time() - stop_recording_start
        print(f"⏱️  TIMING: About to beep at {pre_beep_time:.2f}s")
        logger.info(f"TIMING: Time before beep: {pre_beep_time:.2f}s")
        _beep(beeps_on, *READY_BEEP)
        post_beep_time = time.time() - stop_recording_start
        print(f"⏱️  TIMING: Beep completed at {post_beep_time:.2f}s")
        logger.info(f"TIMING: Time after beep: {post_beep_time:.2f}s")
        if notify_on: _notify("TalkType", f"Transcribed: {text[:80]}{'…' if len(text)>80 else ''}")
        if text:
            # No delay - start injection immediately after transcription

            # Determine injection method (handles auto mode with smart detection)
            # Time this to see if it's causing the delay
            detection_start = time.time()
            print(f"⏱️  TIMING: Starting injection method detection...")
            logger.info("TIMING: Starting injection method detection...")
            actual_mode, use_atspi, reason = _determine_injection_method(injection_mode)
            detection_time = time.time() - detection_start
            print(f"⏱️  TIMING: Injection method detection took {detection_time:.3f}s (mode: {actual_mode})")
            logger.info(f"TIMING: Injection method detection took {detection_time:.3f}s")
            if detection_time > 0.1:  # Log if it takes more than 100ms
                logger.warning(f"⚠️  Injection method detection took {detection_time:.2f}s - this may cause delays!")
            
            # Time the actual injection
            injection_start = time.time()
            logger.info(f"TIMING: Starting text injection (mode: {actual_mode})...")
            
            use_paste = (actual_mode == "paste")
            
            logger.info(f"Injection mode: configured={injection_mode!r}, actual={actual_mode!r}, atspi={use_atspi}, reason={reason}")
            if injection_mode == "auto":
                print(f"🔍 Auto mode: {reason}")

            # Try AT-SPI insertion first if recommended
            if use_atspi:
                logger.info(f"Attempting AT-SPI insertion: {reason}")
                print(f"🔮 Attempting AT-SPI insertion...")
                try:
                    from .atspi_helper import insert_text_atspi
                    if insert_text_atspi(text):
                        print(f"✨ AT-SPI insertion successful! ({len(text)} chars)")
                        logger.info("AT-SPI text insertion succeeded")
                    else:
                        # AT-SPI failed, fall back to typing
                        print(f"⚠️  AT-SPI insertion failed, falling back to typing")
                        logger.warning("AT-SPI insertion failed, using typing fallback")
                        _type_text(text)
                except Exception as e:
                    logger.error(f"AT-SPI insertion error: {e}")
                    print(f"⚠️  AT-SPI error, falling back to typing")
                    _type_text(text)
            # Smart hybrid mode: Split text on markers and paste each chunk separately
            # This gives us fast paste for long text while properly handling formatting commands
            elif use_paste and ("§SHIFT_ENTER§" in text or "\n" in text):
                logger.info(f"Smart hybrid mode: splitting text on markers")

                # Split on §SHIFT_ENTER§ markers
                parts = text.split("§SHIFT_ENTER§")
                logger.info(f"Split into {len(parts)} parts")

                success = True
                for i, part in enumerate(parts):
                    if part:  # Only paste non-empty parts
                        logger.info(f"Pasting part {i+1}/{len(parts)}: {len(part)} chars")
                        if not _paste_text(part):
                            # Paste failed, fall back to typing the whole thing
                            logger.warning(f"Paste failed on part {i+1}, falling back to typing mode")
                            success = False
                            break
                        time.sleep(0.08)  # Brief delay after each paste

                    # Send Shift+Enter after each part except the last
                    if i < len(parts) - 1:
                        logger.info(f"Sending Shift+Enter after part {i+1}")
                        _send_shift_enter()
                        time.sleep(0.05)

                if success:
                    print(f"✂️  Inject (smart paste) {len(parts)} chunks, {len(text)} total chars")
                    logger.info(f"Smart hybrid paste completed: {len(parts)} chunks")
                else:
                    # Fall back to typing mode
                    print(f"⌨️  Inject (type) len={len(text)} [paste failed, typing fallback]")
                    logger.info(f"Falling back to typing mode")
                    _type_text(text)
            elif use_paste and _paste_text(text):
                # Simple paste, no special markers
                injection_time = time.time() - injection_start
                total_time = time.time() - stop_recording_start
                print(f"⏱️  TIMING: Paste injection completed in {injection_time:.2f}s")
                print(f"⏱️  TIMING: TOTAL TIME from stop to text appearing: {total_time:.2f}s")
                logger.info(f"TIMING: Paste injection completed in {injection_time:.2f}s")
                logger.info(f"TIMING: Total time from stop_recording to injection complete: {total_time:.2f}s")
                if injection_time > 1.0:
                    logger.warning(f"⚠️  Paste injection took {injection_time:.2f}s - this is unusually slow!")
                print(f"✂️  Inject (paste) len={len(text)}")
                logger.info(f"Text injected via paste: {len(text)} chars in {injection_time:.2f}s")
            else:
                # Use typing mode
                injection_time = time.time() - injection_start
                total_time = time.time() - stop_recording_start
                logger.info(f"TIMING: Typing injection completed in {injection_time:.2f}s")
                logger.info(f"TIMING: Total time from stop_recording to injection complete: {total_time:.2f}s")
                if injection_time > 1.0:
                    logger.warning(f"⚠️  Typing injection took {injection_time:.2f}s - this is unusually slow!")
                print(f"⌨️  Inject (type) len={len(text)}")
                logger.info(f"Text injected via typing: {len(text)} chars in {injection_time:.2f}s")
                _type_text(text)
            
            # Track the injected text for undo functionality
            state.last_inserted_text = text
            logger.debug(f"Stored last inserted text for undo: {len(text)} chars")
        else:
            print("ℹ️  (No speech recognized)")
            logger.debug("No speech recognized in audio")
    except Exception as e:
            logger.error(f"Transcription error: {e}", exc_info=True)
            print(f"❌ Transcription error: {e}")
            _beep(beeps_on, *READY_BEEP)  # Still play the ready beep so user knows it's done
            if notify_on: _notify("TalkType", f"Transcription failed: {str(e)[:60]}{'…' if len(str(e))>60 else ''}")
    finally:
        # Ensure recording indicator is hidden (already hidden at start of stop_recording)
        pass

def _loop_evdev(cfg: Settings, input_device_idx):
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    print(f"Session: {session} | Wayland={session=='wayland'}")
    logger.info(f"Session type: {session}, Wayland: {session=='wayland'}")
    mode = cfg.mode.lower().strip()
    print(f"Mode: {mode} | Hold key: {cfg.hotkey}" + (f" | Toggle key: {cfg.toggle_hotkey}" if mode=='toggle' else ""))
    logger.info(f"Input mode: {mode}, Hold key: {cfg.hotkey}, Toggle key: {cfg.toggle_hotkey if mode=='toggle' else 'N/A'}")

    # Auto-timeout setup
    timeout_enabled = getattr(cfg, 'auto_timeout_enabled', False)
    timeout_minutes = getattr(cfg, 'auto_timeout_minutes', 5)
    timeout_seconds = timeout_minutes * 60
    last_activity_time = time.time()
    print(f"Auto-timeout: {timeout_enabled} | Timeout: {timeout_minutes} minutes")
    logger.info(f"Auto-timeout: enabled={timeout_enabled}, minutes={timeout_minutes}")

    devices = [InputDevice(p) for p in list_devices()]
    for dev in devices:
        try: dev.set_nonblocking(True)
        except Exception: pass

    # Check if this is the first run BEFORE setting up hotkeys
    # If first run (onboarding not complete), don't monitor ANY keys
    try:
        from talktype.cuda_helper import is_first_run, mark_first_run_complete
        first_run = is_first_run()
    except Exception:
        first_run = False

    if first_run:
        logger.info("First run detected - onboarding not complete")
        logger.info("Service will NOT monitor any keys until onboarding is done")
        print("Onboarding not complete. No hotkeys will be active until setup is finished.")
        return  # Exit - tray will restart service after onboarding

    hold_key = _keycode_from_name(cfg.hotkey)
    toggle_key = _keycode_from_name(cfg.toggle_hotkey) if mode == "toggle" else None

    # If no hotkeys are configured, exit gracefully
    if hold_key is None:
        logger.info("No hotkey configured - service will not monitor any keys")
        logger.info("Hotkeys will be activated after user completes onboarding")
        print("No hotkey configured. Complete onboarding to activate dictation.")
        return  # Exit the service - it will be restarted after onboarding

    # Check if we should show welcome dialog (after user changed keys)
    show_welcome_after_change = False
    from .config import get_data_dir
    welcome_flag_file = os.path.join(get_data_dir(), ".show_welcome_on_restart")
    if os.path.exists(welcome_flag_file):
        show_welcome_after_change = True
        try:
            os.remove(welcome_flag_file)
            logger.info("Removed welcome flag, will show welcome dialog")
        except Exception as e:
            logger.error(f"Failed to remove welcome flag: {e}")

    # Only show hotkey verification on first run
    if first_run:
        # Loop until user verifies or skips
        while True:
            # Initialize hotkey testing
            state.hotkey_test_start_time = time.time()
            state.hold_key_tested = False
            state.toggle_key_tested = False

            # Show hotkey verification dialog
            print(f"🎹 Showing hotkey verification dialog...")
            logger.info(f"Showing hotkey verification dialog for user")

            # Run dialog directly (GTK must run in main thread)
            action, verified = show_hotkey_test_dialog(mode, cfg.hotkey, cfg.toggle_hotkey)

            if action == "change_keys":
                # User wants to change hotkeys
                print("🔧 User wants to change hotkeys...")
                logger.info("Showing simple hotkey change dialog")

                # Show simple hotkey change dialog
                saved, new_mode, new_hold_key, new_toggle_key = show_simple_hotkey_change_dialog(
                    mode, cfg.hotkey, cfg.toggle_hotkey
                )

                if saved:
                    # Save new hotkeys to config
                    print(f"💾 Saving new hotkeys: mode={new_mode}, hold={new_hold_key}, toggle={new_toggle_key}")
                    logger.info(f"User changed hotkeys: mode={new_mode}, hold={new_hold_key}, toggle={new_toggle_key}")

                    # Update config
                    cfg.mode = new_mode
                    cfg.hotkey = new_hold_key
                    cfg.toggle_hotkey = new_toggle_key

                    # Save to file
                    from talktype.config import save_config
                    save_config(cfg)
                    logger.info("Config saved with new hotkeys")

                    # Update mode and keycodes for this session
                    mode = new_mode
                    hold_key = _keycode_from_name(new_hold_key)
                    toggle_key = _keycode_from_name(new_toggle_key) if mode == "toggle" else None

                    # Loop back to verification with new keys
                    print(f"🔄 Now test your new hotkeys: {new_hold_key} and {new_toggle_key}")
                    logger.info("Looping back to verification with new hotkeys")
                    continue  # Go back to start of while loop
                else:
                    print("⚠️ User cancelled hotkey change, returning to verification")
                    logger.info("User cancelled hotkey change, returning to verification")
                    continue  # Go back to verification with original keys

            elif action == "verified" and verified:
                state.hold_key_tested = True
                if mode == "toggle":
                    state.toggle_key_tested = True
                print(f"✓ Hotkeys verified successfully")
                logger.info(f"Hotkeys verified by user")

                # Mark first run as complete
                try:
                    mark_first_run_complete()
                    logger.info("First run marked as complete")
                except Exception as e:
                    logger.error(f"Failed to mark first run complete: {e}")

                break  # Exit the while loop

            else:
                # User skipped verification
                print("⚠️ Hotkey verification skipped by user")
                logger.warning("Hotkey verification skipped")
                break  # Exit the while loop

        # After verification loop, show final ready dialog if verified
        if action == "verified" and verified:

            # Show final "Ready!" message with nice welcome-style dialog
            try:
                gi.require_version('Gtk', '3.0')
                from gi.repository import Gtk

                ready_dialog = Gtk.Dialog(title="Ready to Dictate!")
                ready_dialog.set_default_size(500, 300)
                ready_dialog.set_resizable(False)
                ready_dialog.set_modal(True)
                ready_dialog.set_position(Gtk.WindowPosition.CENTER)

                content = ready_dialog.get_content_area()
                content.set_margin_top(20)
                content.set_margin_bottom(20)
                content.set_margin_start(25)
                content.set_margin_end(25)
                content.set_spacing(15)

                # Main message
                message = Gtk.Label()
                message.set_markup('''<span size="large"><b>✅ You're All Set!</b></span>

<b>🎉 Hotkeys Verified Successfully!</b>

Your hotkeys are working perfectly and ready to use.

<b>🎤 Start Dictating Now:</b>
• Press <b>F8</b> for push-to-talk mode (hold to record)
• Press <b>F9</b> for toggle mode (press once to start, again to stop)

<b>⏱️ Auto-Timeout:</b>
The service will automatically stop after 5 minutes of inactivity
to conserve system resources. Just press your hotkey to wake it up!

<b>📚 Need Help?</b>
Right-click the tray icon → "Help..." for full documentation

<b>Happy dictating! 🚀</b>''')
                message.set_line_wrap(True)
                message.set_xalign(0)
                message.set_yalign(0)
                content.pack_start(message, True, True, 0)

                # Button
                button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                button_box.set_halign(Gtk.Align.CENTER)
                button_box.set_margin_top(10)

                ok_btn = Gtk.Button(label="Let's Go!")
                ok_btn.get_style_context().add_class("suggested-action")
                ok_btn.connect("clicked", lambda w: ready_dialog.response(Gtk.ResponseType.OK))
                button_box.pack_start(ok_btn, False, False, 0)

                content.pack_start(button_box, False, False, 0)

                # Proper GTK dialog handling
                def on_response(dialog, response_id):
                    dialog.destroy()
                    Gtk.main_quit()

                ready_dialog.connect("response", on_response)
                ready_dialog.show_all()

                # Run GTK main loop for this dialog
                Gtk.main()

            except Exception as e:
                logger.error(f"Failed to show ready dialog: {e}")
        elif action == "change_keys":
            print("🔧 User wants to change hotkeys...")
            logger.info("Showing simple hotkey change dialog")

            # Show simple hotkey change dialog
            saved, new_mode, new_hold_key, new_toggle_key = show_simple_hotkey_change_dialog(
                mode, cfg.hotkey, cfg.toggle_hotkey
            )

            if saved:
                # Save new hotkeys to config
                print(f"💾 Saving new hotkeys: mode={new_mode}, hold={new_hold_key}, toggle={new_toggle_key}")
                logger.info(f"User changed hotkeys: mode={new_mode}, hold={new_hold_key}, toggle={new_toggle_key}")

                # Update config
                cfg.mode = new_mode
                cfg.hotkey = new_hold_key
                cfg.toggle_hotkey = new_toggle_key

                # Save to file
                from talktype.config import save_config
                save_config(cfg)
                logger.info("Config saved with new hotkeys")

                # Update mode and keycodes for this session
                mode = new_mode
                hold_key = _keycode_from_name(new_hold_key)
                toggle_key = _keycode_from_name(new_toggle_key) if mode == "toggle" else None

                # Mark first run as complete
                try:
                    mark_first_run_complete()
                    logger.info("First run marked as complete (user changed hotkeys)")
                except Exception as e:
                    logger.error(f"Failed to mark first run complete: {e}")

                # Show success message
                print(f"✅ Hotkeys saved! You can now start dictating with your new keys.")
                logger.info("User finished changing hotkeys, ready to start")
            else:
                print("⚠️ User cancelled hotkey change, skipping verification")
                logger.info("User cancelled hotkey change, continuing with original hotkeys")
        else:
            print("⚠️ Hotkey verification skipped by user")
            logger.warning("Hotkey verification skipped")
    elif show_welcome_after_change:
        # Show welcome dialog after user changed keys (no verification needed)
        print("👋 Showing welcome dialog after hotkey change...")
        logger.info("Showing welcome dialog after user changed hotkeys")
        try:
            gi.require_version('Gtk', '3.0')
            from gi.repository import Gtk

            ready_dialog = Gtk.Dialog(title="Hotkeys Updated!")
            ready_dialog.set_default_size(500, 300)
            ready_dialog.set_resizable(False)
            ready_dialog.set_modal(True)
            ready_dialog.set_position(Gtk.WindowPosition.CENTER)

            content = ready_dialog.get_content_area()
            content.set_margin_top(20)
            content.set_margin_bottom(20)
            content.set_margin_start(25)
            content.set_margin_end(25)
            content.set_spacing(15)

            # Build dynamic hotkey message based on mode
            if mode == "toggle":
                hotkey_msg = f'''<b>🎤 Your New Hotkeys:</b>
• Press <b>{cfg.hotkey}</b> to hold and record (hold mode)
• Press <b>{cfg.toggle_hotkey}</b> to start/stop recording (toggle mode)'''
            else:
                hotkey_msg = f'''<b>🎤 Your New Hotkey:</b>
• Press and hold <b>{cfg.hotkey}</b> to record (push-to-talk mode)'''

            # Main message
            message = Gtk.Label()
            message.set_markup(f'''<span size="large"><b>✅ You're All Set!</b></span>

<b>🎉 Hotkeys Updated Successfully!</b>

Your new hotkeys are ready to use.

{hotkey_msg}

<b>⏱️ Auto-Timeout:</b>
The service will automatically stop after 5 minutes of inactivity
to conserve system resources. Just press your hotkey to wake it up!

<b>📚 Need Help?</b>
Right-click the tray icon → "Help..." for full documentation

<b>Happy dictating! 🚀</b>''')
            message.set_line_wrap(True)
            message.set_xalign(0)
            message.set_yalign(0)
            content.pack_start(message, True, True, 0)

            # Button
            button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            button_box.set_halign(Gtk.Align.CENTER)
            button_box.set_margin_top(10)

            ok_btn = Gtk.Button(label="Let's Go!")
            ok_btn.get_style_context().add_class("suggested-action")
            ok_btn.connect("clicked", lambda w: ready_dialog.response(Gtk.ResponseType.OK))
            button_box.pack_start(ok_btn, False, False, 0)

            content.pack_start(button_box, False, False, 0)

            # Show dialog and wait for response
            ready_dialog.show_all()
            ready_dialog.run()
            ready_dialog.destroy()
            logger.info("Welcome dialog closed, continuing to main loop")

        except Exception as e:
            logger.error(f"Failed to show welcome dialog after hotkey change: {e}")

    # Track which device is grabbed (to prevent hotkey from passing through to apps)
    grabbed_device = None

    while True:
        current_time = time.time()

        # Check for auto-timeout
        if timeout_enabled and not state.is_recording:
            if current_time - last_activity_time > timeout_seconds:
                print(f"⏰ Auto-timeout: No activity for {timeout_minutes} minutes, shutting down...")
                if cfg.notify:
                    _notify("TalkType Auto-Timeout", f"Service stopped after {timeout_minutes} minutes of inactivity")
                sys.exit(0)

        for dev in devices:
            try:
                for event in dev.read():
                    if event.type == ecodes.EV_KEY:
                        if mode == "hold":
                            if event.code == hold_key:
                                # Reset timeout timer only when TalkType hotkey is used
                                if timeout_enabled:
                                    last_activity_time = current_time
                                if event.value == 1 and not state.is_recording:
                                    # Grab ALL keyboard devices to prevent hotkey from passing through to apps
                                    # This stops key repeat on terminals where F-keys produce characters
                                    grabbed_devices = []
                                    for grab_dev in devices:
                                        try:
                                            grab_dev.grab()
                                            grabbed_devices.append(grab_dev)
                                            logger.info(f"Grabbed device: {grab_dev.name}")
                                        except Exception as e:
                                            logger.warning(f"Could not grab {grab_dev.name}: {e}")
                                    grabbed_device = grabbed_devices if grabbed_devices else None
                                    start_recording(cfg.beeps, cfg.notify, input_device_idx)
                                elif event.value == 0 and state.is_recording:
                                    # Ungrab all devices BEFORE text injection so ydotool can work
                                    if grabbed_device:
                                        for ungrab_dev in grabbed_device:
                                            try:
                                                ungrab_dev.ungrab()
                                                logger.info(f"Ungrabbed device: {ungrab_dev.name}")
                                            except Exception:
                                                pass
                                        grabbed_device = None
                                    stop_recording(cfg.beeps, cfg.smart_quotes, cfg.notify, cfg.language, cfg.auto_space, cfg.auto_period, cfg.injection_mode)
                        else:  # toggle mode: press to start, press again to stop
                            if event.code == toggle_key and event.value == 1:
                                # Reset timeout timer only when TalkType hotkey is used
                                if timeout_enabled:
                                    last_activity_time = current_time
                                if not state.is_recording:
                                    start_recording(cfg.beeps, cfg.notify, input_device_idx)
                                else:
                                     stop_recording(cfg.beeps, cfg.smart_quotes, cfg.notify, cfg.language, cfg.auto_space, cfg.auto_period, cfg.injection_mode)
                        # ESC cancels in any mode
                        if event.code == ecodes.KEY_ESC and state.is_recording and event.value == 1:
                            # Reset timeout timer when ESC is used to cancel
                            if timeout_enabled:
                                last_activity_time = current_time
                            cancel_recording(cfg.beeps, cfg.notify, "Cancelled by ESC")
                            # Ungrab all devices if recording was cancelled
                            if grabbed_device:
                                for ungrab_dev in grabbed_device:
                                    try:
                                        ungrab_dev.ungrab()
                                    except Exception:
                                        pass
                                grabbed_device = None
            except BlockingIOError:
                pass
            except Exception:
                pass
        time.sleep(0.005)

def build_model(settings: Settings):
    from .model_helper import download_model_with_progress

    compute_type = "float16" if settings.device.lower() == "cuda" else "int8"
    try:
        # Use model helper with progress dialog
        model = download_model_with_progress(
            settings.model,
            device=settings.device,
            compute_type=compute_type
        )

        if model is None:
            # User cancelled download
            raise Exception("Model download cancelled by user")

        print(f"✅ Model loaded successfully on {settings.device.upper()}")
        logger.info(f"Model loaded: {settings.model} on {settings.device}")
        return model
    except Exception as e:
        if settings.device.lower() == "cuda":
            print(f"❌ CUDA failed: {e}")
            logger.error(f"CUDA error: {type(e).__name__}: {str(e)}")
            import traceback
            logger.debug("CUDA traceback:", exc_info=True)
            print("🔄 Falling back to CPU...")
            try:
                # Try CPU fallback with progress dialog
                model = download_model_with_progress(
                    settings.model,
                    device="cpu",
                    compute_type="int8"
                )

                if model is None:
                    raise Exception("Model download cancelled by user")

                print("✅ Model loaded successfully on CPU (fallback)")
                logger.info("Model loaded on CPU (fallback from CUDA)")
                return model
            except Exception as cpu_e:
                print(f"❌ CPU fallback also failed: {cpu_e}")
                logger.error(f"CPU fallback failed: {cpu_e}")
                raise cpu_e
        else:
            print(f"❌ Model loading failed: {e}")
            logger.error(f"Model loading failed: {e}")
            raise e

def parse_args():
    ap = argparse.ArgumentParser(prog="dictate", description="Press-and-hold / toggle dictation for Wayland")
    ap.add_argument("--model", help="Whisper model (tiny/base/small/medium/large-v3)", default=None)
    ap.add_argument("--device", help="Device (cpu/cuda)", default=None)
    ap.add_argument("--hotkey", help="Hold-to-talk hotkey (F1..F12 or a-z)", default=None)
    ap.add_argument("--mode", choices=["hold","toggle"], help="Activation mode", default=None)
    ap.add_argument("--toggle-hotkey", help="Toggle key (F1..F12 or a-z) when mode=toggle", default=None)
    ap.add_argument("--mic", help="Substring of input device name to use", default=None)
    ap.add_argument("--beeps", choices=["on","off"], help="Enable beeps", default=None)
    ap.add_argument("--smart-quotes", choices=["on","off"], help="Use “smart quotes”", default=None)
    ap.add_argument("--notify", choices=["on","off"], help="Desktop notifications", default=None)
    ap.add_argument("--language", help="Force language code (e.g., en). Empty = auto-detect", default=None)
    return ap.parse_args()

def main():
    _acquire_single_instance()

    cfg = load_config()
    args = parse_args()

    if args.model: cfg.model = args.model
    if args.device: cfg.device = args.device
    if args.hotkey: cfg.hotkey = args.hotkey
    if args.mode: cfg.mode = args.mode
    if args.toggle_hotkey: cfg.toggle_hotkey = args.toggle_hotkey
    if args.mic is not None: cfg.mic = args.mic
    if args.beeps: cfg.beeps = (args.beeps == "on")
    if args.smart_quotes: cfg.smart_quotes = (args.smart_quotes == "on")
    if args.notify: cfg.notify = (args.notify == "on")
    if args.language is not None: cfg.language = args.language

    # Set global typing delay from config
    global _typing_delay
    _typing_delay = getattr(cfg, 'typing_delay', 12)
    logger.debug(f"Typing delay set to {_typing_delay}ms")

    # Load custom voice commands
    global _custom_commands
    _custom_commands = load_custom_commands()
    if _custom_commands:
        logger.info(f"Loaded {len(_custom_commands)} custom voice command(s)")
        print(f"✓ Loaded {len(_custom_commands)} custom voice command(s)")

    # Input device selection
    input_device_idx = _pick_input_device(cfg.mic)

    # Initialize GTK components (D-Bus service and recording indicator)
    # Both need the GTK main loop, so we initialize them together
    global dbus_service, recording_indicator
    dbus_service = None
    recording_indicator = None
    gtk_needed = False

    # Check if we need GTK at all
    if cfg.recording_indicator or True:  # Always try D-Bus for GNOME extension
        gtk_needed = True

    if gtk_needed:
        try:
            # Import GTK in the main thread
            import gi
            gi.require_version('Gtk', '3.0')
            from gi.repository import Gtk, GLib

            # Initialize D-Bus service for GNOME extension integration
            try:
                from .dbus_service import TalkTypeDBusService

                # Create a simple app instance with necessary attributes for D-Bus
                class AppInstance:
                    def __init__(self, cfg):
                        self.config = cfg
                        self.is_recording = False
                        self.service_running = True
                        self.dbus_service = None

                    def show_preferences(self):
                        """Open preferences window"""
                        import subprocess
                        subprocess.Popen([sys.executable, "-m", "talktype.prefs"])

                    def start_recording(self):
                        """Start recording - not implemented in D-Bus only mode"""
                        pass

                    def stop_recording(self):
                        """Stop recording - not implemented in D-Bus only mode"""
                        pass

                    def toggle_recording(self):
                        """Toggle recording - not implemented in D-Bus only mode"""
                        pass

                    def start_service(self):
                        """Start the dictation service"""
                        import subprocess
                        try:
                            # Find the dictate script
                            src_dir = os.path.dirname(__file__)  # usr/src/talktype
                            usr_dir = os.path.dirname(os.path.dirname(src_dir))  # usr
                            dictate_script = os.path.join(usr_dir, "bin", "dictate")

                            if os.path.exists(dictate_script):
                                subprocess.Popen([dictate_script], env=os.environ.copy())
                                logger.info(f"Started dictation service via {dictate_script}")
                            else:
                                subprocess.Popen([sys.executable, "-m", "talktype.app"],
                                               env=os.environ.copy())
                                logger.info("Started dictation service via Python module")

                            self.service_running = True
                            if self.dbus_service:
                                self.dbus_service.emit_service_state(True)
                        except Exception as e:
                            logger.error(f"Failed to start service: {e}", exc_info=True)

                    def stop_service(self):
                        """Stop the dictation service"""
                        import subprocess
                        try:
                            subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
                            logger.info("Stopped dictation service")
                            self.service_running = False
                            if self.dbus_service:
                                self.dbus_service.emit_service_state(False)
                        except Exception as e:
                            logger.error(f"Failed to stop service: {e}", exc_info=True)

                    def set_model(self, model_name: str):
                        """Change the Whisper model (requires service restart)"""
                        try:
                            # Update config file
                            from .config import load_config
                            config_path = os.path.expanduser("~/.config/talktype/settings.json")

                            # Read current config
                            import json
                            if os.path.exists(config_path):
                                with open(config_path, 'r') as f:
                                    config_data = json.load(f)
                            else:
                                config_data = {}

                            # Update model
                            config_data['model'] = model_name
                            self.config.model = model_name

                            # Write back
                            os.makedirs(os.path.dirname(config_path), exist_ok=True)
                            with open(config_path, 'w') as f:
                                json.dump(config_data, f, indent=2)

                            logger.info(f"Model changed to {model_name} (restart required)")

                            # Emit signal so extension updates
                            if self.dbus_service:
                                self.dbus_service.emit_model_changed(model_name)

                            # Note: Actual model change requires service restart
                            # For now, we just update config and notify
                        except Exception as e:
                            logger.error(f"Failed to set model: {e}", exc_info=True)

                    def quit(self):
                        """Quit the application"""
                        import subprocess
                        try:
                            subprocess.run(["pkill", "-f", "talktype"], capture_output=True)
                        except Exception:
                            pass
                        sys.exit(0)

                app_instance = AppInstance(cfg)
                dbus_service = TalkTypeDBusService(app_instance)
                app_instance.dbus_service = dbus_service

                # Emit initial state so extension syncs properly
                dbus_service.emit_service_state(True)
                dbus_service.emit_model_changed(cfg.model)

                print("✓ D-Bus service initialized for GNOME extension")
                logger.info("D-Bus service started successfully")
            except Exception as e:
                print(f"⚠️  Failed to initialize D-Bus service: {e}")
                logger.error(f"D-Bus service initialization failed: {e}", exc_info=True)

            # Initialize recording indicator if enabled
            if cfg.recording_indicator:
                try:
                    recording_indicator = RecordingIndicator(
                        position=cfg.indicator_position,
                        offset_x=cfg.indicator_offset_x,
                        offset_y=cfg.indicator_offset_y,
                        size=cfg.indicator_size
                    )
                    print(f"✓ Recording indicator initialized (position: {cfg.indicator_position}, size: {cfg.indicator_size})")
                    logger.info(f"Recording indicator initialized at position: {cfg.indicator_position}, size: {cfg.indicator_size}")
                except Exception as e:
                    print(f"⚠️  Failed to initialize recording indicator: {e}")
                    logger.error(f"Recording indicator initialization failed: {e}", exc_info=True)

            # Start single GTK main loop in a background thread for both D-Bus and recording indicator
            def run_gtk_loop():
                print("🔄 Starting GTK main loop...")
                Gtk.main()

            gtk_thread = threading.Thread(target=run_gtk_loop, daemon=True)
            gtk_thread.start()
            print("✓ GTK main loop started in background thread")

        except Exception as e:
            print(f"⚠️  Failed to initialize GTK components: {e}")
            logger.error(f"GTK initialization failed: {e}", exc_info=True)

    global model
    model = build_model(cfg)
    print(f"Config: model={cfg.model} device={cfg.device} lang={cfg.language or 'auto'} auto_space={cfg.auto_space} auto_period={cfg.auto_period}")
    logger.info(f"Configuration: model={cfg.model}, device={cfg.device}, language={cfg.language or 'auto'}, auto_space={cfg.auto_space}, auto_period={cfg.auto_period}")
    _loop_evdev(cfg, input_device_idx)

if __name__ == "__main__":
    main()

import os
# CRITICAL: Disable HuggingFace XET downloads BEFORE any imports
# XET bypasses tqdm_class progress tracking, breaking our download progress UI
os.environ["HF_HUB_DISABLE_XET"] = "1"

# Import torch_init FIRST to configure CUDA library paths before any torch imports
from .torch_init import init_cuda_for_pytorch
init_cuda_for_pytorch()

import sys, time, re, shutil, subprocess, tempfile, wave, atexit, argparse, fcntl, signal
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

# Cached tool path lookups — avoids searching PATH on every text injection
_tool_cache = {}
def _which(name):
    """Cached shutil.which() — tools don't move during a session."""
    if name not in _tool_cache:
        _tool_cache[name] = shutil.which(name)
    return _tool_cache[name]

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

# NOTE: Hotkey test/change dialogs live in welcome_dialog.py (used during onboarding).
# The old app.py versions were removed — they were unreachable dead code.

# --- Single instance lock (user runtime dir) ---
def _runtime_dir():
    return os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

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

# ---------------------------------------------------------------------------
# Ydotool environment helper — used by all ydotool calls to set socket path
# ---------------------------------------------------------------------------
def _get_ydotool_env():
    """Return env dict with YDOTOOL_SOCKET set for subprocess calls."""
    env = os.environ.copy()
    runtime = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    env.setdefault("YDOTOOL_SOCKET", os.path.join(runtime, ".ydotool_socket"))
    return env

# ---------------------------------------------------------------------------
# Constants that never change but were being recreated on every call
# ---------------------------------------------------------------------------

# Hotkey options offered in the setup dialogs (F-keys, listed in preferred order)
HOTKEY_OPTIONS = ["F8", "F9", "F10", "F11", "F12", "F1", "F2", "F3", "F4", "F5", "F6", "F7"]

# Voice command patterns for undo functionality
UNDO_PATTERNS = {
    'word': ['undo last word', 'undo the last word', 'delete last word', 'remove last word'],
    'sentence': ['undo last sentence', 'undo the last sentence', 'delete last sentence', 'remove last sentence'],
    'paragraph': ['undo last paragraph', 'undo the last paragraph', 'delete last paragraph', 'remove last paragraph'],
    'everything': ['undo everything', 'undo all', 'delete everything', 'delete all', 'clear everything', 'clear all'],
}

# VAD parameters tuned for dictation (used by faster-whisper transcription)
# - Lower threshold (0.35) = less aggressive at cutting off speech
# - Higher speech_pad_ms (600) = more padding around detected speech
# - Higher min_silence_duration_ms (2500) = longer silence needed to split
VAD_PARAMS = {
    "threshold": 0.35,
    "speech_pad_ms": 600,
    "min_silence_duration_ms": 2500,
}

# D-Bus proxy for notifying the tray process of recording state changes.
# The tray owns the D-Bus name and relays signals to the GNOME extension.
_tray_dbus_proxy = None

# Thread-safe recording command flags — set by signal handler or D-Bus thread, consumed by evdev loop.
# Using two separate Events (rather than one flag) so start and stop can't overwrite each other.
_cmd_start_recording = threading.Event()
_cmd_stop_recording = threading.Event()

def _handle_sigusr1(signum, frame):
    """SIGUSR1 = toggle recording. Sent by the tray process via os.kill().
    Sets the appropriate Event; the evdev loop consumes it from the main thread.
    """
    if state.is_recording:
        _cmd_stop_recording.set()
    else:
        _cmd_start_recording.set()

def _notify_tray_recording_state(is_recording: bool):
    """Send recording state to the tray's D-Bus service.

    The tray process owns the D-Bus name that the GNOME extension listens to.
    App.py cannot emit signals that the extension will see, so we call
    the tray's NotifyRecordingState method which then emits the signal.
    """
    global _tray_dbus_proxy
    try:
        import dbus
        if _tray_dbus_proxy is None:
            import dbus.mainloop.glib
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            bus = dbus.SessionBus()
            _tray_dbus_proxy = bus.get_object(
                'io.github.ronb1964.TalkType',
                '/io/github/ronb1964/TalkType'
            )
        _tray_dbus_proxy.NotifyRecordingState(
            dbus.Boolean(is_recording),
            dbus_interface='io.github.ronb1964.TalkType'
        )
    except Exception as e:
        logger.debug(f"Could not notify tray of recording state: {e}")

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


# YouTube-specific phrases that are NEVER real dictation.
# Safe to strip from the end of any transcription.
_YOUTUBE_HALLUCINATION_PHRASES = [
    "thanks for watching",
    "thanks for listening",
    "thank you for watching",
    "thank you for listening",
    "see you next time",
    "see you in the next video",
    "see you in the next one",
    "subscribe",
    "like and subscribe",
    "please subscribe",
    "don't forget to subscribe",
    "hit the bell",
]

# Common words/phrases that Whisper hallucinates from silence.
# These are only stripped when they are the ENTIRE transcription,
# because they could also be real speech at the end of a sentence
# (e.g., "I want to say thank you" should keep "thank you").
_WHOLE_TEXT_HALLUCINATION_PHRASES = [
    "thank you",
    "thank you very much",
    "thank you so much",
    "thanks",
    "bye",
    "bye bye",
    "goodbye",
    "you",
    "oh",
    "ah",
    "hmm",
    "uh",
    "um",
]


def _strip_hallucinations(text: str, no_speech_prob: float = 0.0) -> str:
    """
    Remove common Whisper hallucination phrases from transcribed text.

    Two-tier approach:
    1. YouTube-specific phrases ("thanks for watching", "like and subscribe")
       are always stripped from the end - nobody dictates these.
    2. Common words ("thank you", "bye") are only discarded when they are
       the ENTIRE transcription AND Whisper's no_speech_prob indicates
       it likely wasn't real speech. This preserves intentional dictation
       of phrases like "Thank you."

    Args:
        text: Raw transcribed text
        no_speech_prob: Whisper's estimate (0-1) that the audio contained
            no real speech. High values (>0.6) suggest hallucination.

    Returns:
        Text with hallucination phrases removed
    """
    if not text:
        return text

    original = text
    text = text.strip()

    # Strip any trailing punctuation for comparison
    lower_clean = text.lower().rstrip(" .,!?;:")

    # Tier 1: If the ENTIRE text is a common hallucination phrase AND
    # Whisper thinks there was no real speech, discard it.
    # This catches silence -> "Thank you." while preserving real "Thank you."
    if lower_clean in _WHOLE_TEXT_HALLUCINATION_PHRASES and no_speech_prob > 0.6:
        logger.info(f"Stripped whole-text hallucination (no_speech_prob={no_speech_prob:.2f}): {original!r}")
        return ""

    # Tier 2: Strip YouTube-specific phrases from the end of text.
    # These are never real dictation so they're always safe to remove.
    changed = True
    while changed:
        changed = False
        lower_text = text.lower()

        for phrase in _YOUTUBE_HALLUCINATION_PHRASES:
            # Check if text ends with this phrase (with optional trailing punctuation)
            stripped = lower_text.rstrip(" .,!?;:")
            if stripped.endswith(phrase):
                # Find where the hallucination starts
                phrase_start = stripped.rfind(phrase)
                if phrase_start > 0:
                    # Remove the hallucination and any trailing punctuation/whitespace
                    text = text[:phrase_start].rstrip(" .,!?;:")
                    changed = True
                    break
                elif phrase_start == 0:
                    # The entire text is just the hallucination
                    text = ""
                    changed = True
                    break

    if text != original:
        logger.info(f"Stripped hallucination: {original!r} -> {text!r}")

    return text


_cached_output_device = None
_output_device_cached = False

def _find_output_device():
    """Find a working output device. Cached — device doesn't change during a session."""
    global _cached_output_device, _output_device_cached
    if _output_device_cached:
        return _cached_output_device
    for name_hint in ['pipewire', 'pulse', 'sysdefault', 'default']:
        for i, d in enumerate(sd.query_devices()):
            if d['max_output_channels'] > 0 and name_hint in d.get('name', '').lower():
                try:
                    sd.check_output_settings(device=i, samplerate=44100, channels=1)
                    _cached_output_device = i
                    _output_device_cached = True
                    return i
                except Exception:
                    continue
    _output_device_cached = True  # Cache the "not found" result too
    return None  # Fall back to sounddevice default

def _beep(enabled: bool, freq=1000, duration=0.15):
    if not enabled:
        return
    samplerate = 44100
    t = np.linspace(0, duration, int(samplerate * duration), False)
    tone = (np.sin(freq * t * 2 * np.pi) * 0.2).astype(np.float32)
    try:
        sd.play(tone, samplerate, device=_find_output_device()); sd.wait()
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
    """Return device index for the best matching input device.

    Delegates to config.find_input_device() which handles PipeWire
    auto-detection when no mic name is configured. This avoids the
    broken ALSA "default" virtual device that returns garbage audio
    on PipeWire systems.
    """
    from .config import find_input_device
    return find_input_device(mic_substring)

def _get_device_samplerate(device_idx):
    """Get the native sample rate for a device, falling back to SAMPLE_RATE.

    Some ALSA hw: devices only support their native rate (e.g. 48000 Hz)
    and reject 16000 Hz. We detect this and record at the native rate,
    then resample to 16000 Hz afterward.
    """
    try:
        sd.check_input_settings(device=device_idx, samplerate=SAMPLE_RATE, channels=CHANNELS)
        return SAMPLE_RATE  # Device supports 16kHz directly
    except sd.PortAudioError:
        pass
    # Fall back to device's default sample rate
    try:
        info = sd.query_devices(device_idx)
        native_sr = int(info['default_samplerate'])
        sd.check_input_settings(device=device_idx, samplerate=native_sr, channels=CHANNELS)
        print(f"ℹ️  Mic doesn't support {SAMPLE_RATE}Hz, recording at {native_sr}Hz (will resample)")
        return native_sr
    except Exception:
        return SAMPLE_RATE  # Last resort, let it fail naturally

def _resample_audio(audio, orig_sr, target_sr):
    """Resample audio from orig_sr to target_sr using linear interpolation.

    Good enough for speech audio going to Whisper. No extra dependencies needed.
    """
    if orig_sr == target_sr:
        return audio
    # Calculate new length and interpolate
    duration = len(audio) / orig_sr
    target_len = int(duration * target_sr)
    orig_indices = np.linspace(0, len(audio) - 1, target_len)
    return np.interp(orig_indices, np.arange(len(audio)), audio.astype(np.float64)).astype(audio.dtype)

def start_recording(beeps_on: bool, notify_on: bool, input_device_idx):
    state.frames = []
    state.was_cancelled = False
    state.is_recording = True
    state.press_t0 = time.time()
    # Use the device's native sample rate (may differ from 16kHz on ALSA hw: devices)
    state.recording_samplerate = _get_device_samplerate(input_device_idx)
    sd.default.channels = CHANNELS
    sd.default.samplerate = state.recording_samplerate
    state.stream = sd.InputStream(callback=_sd_callback, dtype='int16', device=input_device_idx)
    state.stream.start()
    print("🎙️  Recording…")
    logger.debug("Recording started")
    _beep(beeps_on, *START_BEEP)
    if notify_on: _notify("TalkType", "Recording… (speak now)")

    # Notify GNOME extension that recording started (turns icon red)
    _notify_tray_recording_state(True)

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

    # Notify GNOME extension that recording stopped (icon returns to normal)
    _notify_tray_recording_state(False)

def _send_shift_enter():
    """Send Shift+Enter keystrokes to create line break without submitting."""
    if _which("ydotool"):
        try:
            env = _get_ydotool_env()
            # KEY_LEFTSHIFT (42), KEY_ENTER (28)
            subprocess.run(["ydotool", "key", "42:1", "28:1", "28:0", "42:0"], check=False, env=env)
            return True
        except Exception as e:
            logger.debug(f"ydotool shift+enter failed: {e}")
    return False

def _send_enter():
    """Send Enter keystroke to create a new line."""
    if _which("ydotool"):
        try:
            env = _get_ydotool_env()
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
    
    if _which("ydotool"):
        try:
            env = _get_ydotool_env()
            # -d = delay between keydown and keyup (ms)
            # -H = hold time before next key (ms)
            # Lower values are faster but may cause letters to arrive out of order
            delay_str = str(max(5, min(50, _typing_delay)))  # Clamp to 5-50ms
            logger.info(f"ydotool type: delay={delay_str}ms, text_len={len(text)}")
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
    if _which("wtype"):
        subprocess.run(["wtype", "--", text], check=False); return
    if _which("wl-copy"):
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
        if _which("wl-copy") and _which("ydotool"):
            # Always use Ctrl+Shift+V for paste - works in both terminals and regular apps
            # This avoids complex and unreliable terminal detection
            # (Ctrl+Shift+V works universally on Wayland/GNOME)
            
            # Copy text to clipboard
            # wl-copy needs to stay running to serve clipboard requests
            paste_start = time.time()
            logger.info(f"TIMING: Starting paste operation for {len(text)} chars")
            proc = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            proc.stdin.write(text.encode("utf-8"))
            proc.stdin.close()
            wl_copy_time = time.time() - paste_start
            logger.info(f"TIMING: wl-copy started in {wl_copy_time:.3f}s")

            # Wait for clipboard to be ready (needs time for wl-copy to set up)
            time.sleep(0.08)

            # Send Ctrl+Shift+V to paste - works universally in terminals and regular apps
            # KEY_LEFTSHIFT (42), KEY_LEFTCTRL (29), KEY_V (47)
            env = _get_ydotool_env()

            ydotool_start = time.time()
            # Always use Ctrl+Shift+V - works for both terminals and regular apps
            logger.debug("Using Ctrl+Shift+V for paste (universal)")
            # KEY_LEFTSHIFT=42, KEY_LEFTCTRL=29, KEY_V=47
            # Format: keycode:1 (down) or keycode:0 (up)
            subprocess.run(["ydotool", "key",
                    "42:1", "29:1", "47:1", "47:0", "29:0", "42:0"],
                   check=False, env=env)
            ydotool_time = time.time() - ydotool_start
            logger.info(f"TIMING: ydotool paste command took {ydotool_time:.3f}s")

            # Brief delay for paste to register, then terminate wl-copy
            time.sleep(0.05)
            total_paste_time = time.time() - paste_start
            logger.info(f"TIMING: Total paste operation time: {total_paste_time:.3f}s")
            try:
                proc.terminate()
                proc.wait(timeout=0.3)
            except Exception:
                pass  # wl-copy cleanup is best-effort

            return True
    except subprocess.TimeoutExpired as e:
        logger.error(f"Paste injection timeout: {e}")
    except Exception as e:
        logger.error(f"Paste injection failed: {e}")
        pass
    return False

def _press_space():
    # Inject a literal Space keypress via ydotool when possible; fallback to typing a space
    if _which("ydotool"):
        try:
            env = _get_ydotool_env()
            subprocess.run(["ydotool", "key", "57:1", "57:0"], check=False, env=env)
            return
        except Exception:
            pass
    if _which("wtype"):
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
    if _which("ydotool"):
        try:
            env = _get_ydotool_env()
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
    normalized = re.sub(r'[^\w\s]', '', raw_text.lower()).strip()
    normalized = ' '.join(normalized.split())  # Collapse whitespace
    
    # Match undo commands - be flexible with variations Whisper might produce
    for undo_type, patterns in UNDO_PATTERNS.items():
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

def _transcribe_audio(audio_f32, language: str | None) -> str | None:
    """Run Whisper transcription on audio and filter hallucinations.

    Returns the raw transcribed text, or None if no speech was detected.
    """
    transcribe_start = time.time()
    segments, _ = model.transcribe(
        audio_f32,
        vad_filter=True,
        vad_parameters=VAD_PARAMS,
        beam_size=1,
        condition_on_previous_text=False,
        temperature=0.0,
        without_timestamps=True,
        language=(language or None),
        # NOTE: hallucination_silence_threshold was removed because it
        # silently drops real speech after natural 2+ second pauses,
        # causing middle sentences to vanish from longer paragraphs.
        # Hallucination filtering is handled by _strip_hallucinations().
    )
    transcribe_time = time.time() - transcribe_start
    logger.info(f"TIMING: Transcription completed in {transcribe_time:.2f}s")
    if transcribe_time > 2.0:
        logger.warning(f"\u26a0\ufe0f  Transcription took {transcribe_time:.2f}s (first run may be slower due to CUDA compilation)")

    # Collect segments (generator can only be consumed once)
    seg_list = list(segments)
    raw = " ".join(seg.text for seg in seg_list).strip()
    max_no_speech_prob = max((seg.no_speech_prob for seg in seg_list), default=0.0)
    print(f"\U0001f4dd Raw (before filter): {raw!r}  [no_speech_prob={max_no_speech_prob:.2f}]")
    logger.info(f"Raw transcription (before hallucination filter): {raw!r}  [no_speech_prob={max_no_speech_prob:.2f}]")

    # Strip common Whisper hallucinations like "thank you" from the end
    raw = _strip_hallucinations(raw, no_speech_prob=max_no_speech_prob)
    if raw:
        print(f"\U0001f4dd Raw (after filter): {raw!r}")
        logger.info(f"Raw transcription (after hallucination filter): {raw!r}")
    return raw or None


def _handle_undo(raw: str, beeps_on: bool, notify_on: bool) -> bool:
    """Check if raw text is an undo command and execute it.

    Returns True if an undo was handled (caller should return early).
    """
    undo_type = _detect_undo_command(raw)
    if not undo_type:
        return False

    logger.info(f"Undo command detected: {undo_type}")
    print(f"\U0001f519 Undo command: {undo_type}")

    if not state.last_inserted_text:
        print("\u2139\ufe0f  Nothing to undo (no previous dictation)")
        logger.info("Undo requested but no previous text to undo")
        _beep(beeps_on, *CANCEL_BEEP)
        if notify_on: _notify("TalkType", "Nothing to undo")
        return True

    # Calculate how many characters to delete
    delete_count = _calculate_undo_length(state.last_inserted_text, undo_type)
    logger.info(f"Undo: deleting {delete_count} characters (last text was {len(state.last_inserted_text)} chars)")
    print(f"\U0001f519 Undoing {delete_count} characters ({undo_type})")

    if delete_count > 0:
        _send_backspaces(delete_count)
        # Update last_inserted_text to reflect what remains
        if delete_count >= len(state.last_inserted_text):
            state.last_inserted_text = ""
            state.continue_mid_sentence = False
        else:
            state.last_inserted_text = state.last_inserted_text[:-delete_count]
            remaining = state.last_inserted_text.rstrip()
            if remaining and not remaining.endswith(('.', '?', '!', '\u2026')):
                state.continue_mid_sentence = True
                logger.info("Mid-sentence continuation enabled for next dictation")
            else:
                state.continue_mid_sentence = False
        _beep(beeps_on, *READY_BEEP)
        if notify_on: _notify("TalkType", f"Undid last {undo_type}")
    else:
        print("\u2139\ufe0f  Nothing to undo for this scope")
        _beep(beeps_on, *CANCEL_BEEP)
    return True


def _prepare_text(raw: str, smart_quotes: bool, auto_period: bool, auto_space: bool) -> str:
    """Apply voice commands, normalize, handle mid-sentence, add auto-period/space.

    Returns the final text string ready for injection.
    """
    # Apply custom voice commands (phrase \u2192 replacement)
    processed = _apply_custom_commands(raw)

    # Normalize text (capitalization, punctuation, etc.)
    text = normalize_text(processed if smart_quotes else processed.replace("\u201c","\"").replace("\u201d","\""))

    # Handle mid-sentence continuation after undo:
    # lowercase the first letter if we're continuing a sentence
    if state.continue_mid_sentence and text:
        if text[0].isupper():
            text = text[0].lower() + text[1:]
            logger.info("Lowercased first letter for mid-sentence continuation")
        state.continue_mid_sentence = False

    # Auto-period and auto-space (skip if text contains line break markers)
    has_break_markers = "\xa7SHIFT_ENTER\xa7" in text
    text_without_markers = text.replace("\xa7SHIFT_ENTER\xa7", "").strip()
    is_only_markers = has_break_markers and not text_without_markers

    if auto_period and text and not is_only_markers and not text.rstrip().endswith((".","?","!","\u2026")):
        text = text.rstrip() + "."
    if auto_space and text and not is_only_markers and not text.endswith((" ", "\n", "\t")):
        text = text + " "
    logger.info(f"Normalized text: {text!r}")
    return text


def _inject_text(text: str, injection_mode: str, t0: float):
    """Determine the best injection method and insert text into the active app.

    Tries AT-SPI first (if auto mode recommends it), then paste, then typing.
    t0 is the timestamp when stop_recording began (for timing logs).
    """
    # Determine injection method (auto mode does smart detection)
    detection_start = time.time()
    actual_mode, use_atspi, reason = _determine_injection_method(injection_mode)
    detection_time = time.time() - detection_start
    logger.info(f"TIMING: Injection method detection took {detection_time:.3f}s")
    if detection_time > 0.1:
        logger.warning(f"Injection method detection slow: {detection_time:.2f}s")

    injection_start = time.time()
    use_paste = (actual_mode == "paste")
    logger.info(f"Injection mode: configured={injection_mode!r}, actual={actual_mode!r}, atspi={use_atspi}, reason={reason}")
    if injection_mode == "auto":
        print(f"\U0001f50d Auto mode: {reason}")

    # --- AT-SPI insertion (accessibility API, fastest when supported) ---
    if use_atspi:
        logger.info(f"Attempting AT-SPI insertion: {reason}")
        print("\U0001f52e Attempting AT-SPI insertion...")
        try:
            from .atspi_helper import insert_text_atspi
            if insert_text_atspi(text):
                print(f"\u2728 AT-SPI insertion successful! ({len(text)} chars)")
                logger.info("AT-SPI text insertion succeeded")
            else:
                print("\u26a0\ufe0f  AT-SPI insertion failed, falling back to typing")
                logger.warning("AT-SPI insertion failed, using typing fallback")
                _type_text(text)
        except Exception as e:
            logger.error(f"AT-SPI insertion error: {e}")
            print("\u26a0\ufe0f  AT-SPI error, falling back to typing")
            _type_text(text)

    # --- Smart hybrid paste (text with line-break markers) ---
    elif use_paste and ("\xa7SHIFT_ENTER\xa7" in text or "\n" in text):
        logger.info("Smart hybrid mode: splitting text on markers")
        parts = text.split("\xa7SHIFT_ENTER\xa7")
        logger.info(f"Split into {len(parts)} parts")
        success = True
        for i, part in enumerate(parts):
            if part:
                logger.info(f"Pasting part {i+1}/{len(parts)}: {len(part)} chars")
                if not _paste_text(part):
                    logger.warning(f"Paste failed on part {i+1}, falling back to typing mode")
                    success = False
                    break
                time.sleep(0.08)
            if i < len(parts) - 1:
                logger.info(f"Sending Shift+Enter after part {i+1}")
                _send_shift_enter()
                time.sleep(0.05)
        if success:
            print(f"\u2702\ufe0f  Inject (smart paste) {len(parts)} chunks, {len(text)} total chars")
            logger.info(f"Smart hybrid paste completed: {len(parts)} chunks")
        else:
            print(f"\u2328\ufe0f  Inject (type) len={len(text)} [paste failed, typing fallback]")
            _type_text(text)

    # --- Simple paste (no markers) ---
    elif use_paste and _paste_text(text):
        injection_time = time.time() - injection_start
        total_time = time.time() - t0
        logger.info(f"TIMING: Paste injection completed in {injection_time:.2f}s")
        logger.info(f"Text injected via paste: {len(text)} chars in {injection_time:.2f}s")
        if injection_time > 1.0:
            logger.warning(f"Paste injection slow: {injection_time:.2f}s")

    # --- Typing fallback ---
    else:
        _type_text(text)
        injection_time = time.time() - injection_start
        logger.info(f"TIMING: Typing injection completed in {injection_time:.2f}s")
        logger.info(f"Text injected via typing: {len(text)} chars in {injection_time:.2f}s")
        if injection_time > 1.0:
            logger.warning(f"Typing injection slow: {injection_time:.2f}s")

    # Track injected text for undo functionality
    state.last_inserted_text = text
    logger.debug(f"Stored last inserted text for undo: {len(text)} chars")


def stop_recording(
    beeps_on: bool,
    smart_quotes: bool,
    notify_on: bool,
    language: str | None = None,
    auto_space: bool = True,
    auto_period: bool = True,
    injection_mode: str = "type",
):
    """Stop recording, transcribe audio, and inject text into the active app.

    Pipeline: validate \u2192 convert audio \u2192 transcribe \u2192 check undo \u2192 prepare \u2192 beep \u2192 inject
    """
    held_ms = int((time.time() - (state.press_t0 or time.time())) * 1000)
    if held_ms < MIN_HOLD_MS:
        cancel_recording(beeps_on, notify_on, f"Cancelled (held {held_ms} ms)"); return
    state.is_recording = False
    _stop_stream_safely()
    _notify_tray_recording_state(False)  # Tell GNOME extension recording stopped
    if state.was_cancelled: return

    # Hide recording indicator before text injection
    if recording_indicator:
        recording_indicator.hide_indicator()

    print("🛑 Recording stopped. Transcribing…")
    t0 = time.time()
    logger.info("Recording stopped, starting transcription")

    try:
        # Convert captured bytes \u2192 float32 mono PCM in [-1, 1]
        pcm_int16 = np.frombuffer(b''.join(state.frames), dtype=np.int16)
        if pcm_int16.size == 0:
            print("\u2139\ufe0f  (No audio captured)")
            return
        audio_f32 = pcm_int16.astype(np.float32) / 32768.0
        rec_sr = getattr(state, 'recording_samplerate', SAMPLE_RATE)
        if rec_sr != SAMPLE_RATE:
            audio_f32 = _resample_audio(audio_f32, rec_sr, SAMPLE_RATE)

        # Stage 1: Transcribe audio \u2192 raw text
        raw = _transcribe_audio(audio_f32, language)
        post_transcribe = time.time() - t0
        logger.info(f"TIMING: Transcription pipeline took {post_transcribe:.2f}s")
        if not raw:
            print("\u2139\ufe0f  (No speech recognized)")
            return

        # Stage 2: Check for undo commands ("undo that", "undo word", etc.)
        if _handle_undo(raw, beeps_on, notify_on):
            return

        # Stage 3: Normalize text (voice commands, punctuation, spacing)
        text = _prepare_text(raw, smart_quotes, auto_period, auto_space)

        # Beep to confirm transcription is done
        _beep(beeps_on, *READY_BEEP)
        if notify_on: _notify("TalkType", f"Transcribed: {text[:80]}{'\u2026' if len(text)>80 else ''}")

        # Stage 4: Inject text into the active application
        if text:
            _inject_text(text, injection_mode, t0)

    except Exception as e:
        logger.error(f"Transcription error: {e}", exc_info=True)
        print(f"\u274c Transcription error: {e}")
        _beep(beeps_on, *READY_BEEP)
        if notify_on: _notify("TalkType", f"Transcription failed: {str(e)[:60]}{'\u2026' if len(str(e))>60 else ''}")

def _show_welcome_after_change(cfg, mode):
    """Show 'Hotkeys Updated!' dialog after user changed keys via Preferences.

    This runs once before the main event loop when a flag file is present.
    """
    print("\U0001f44b Showing welcome dialog after hotkey change...")
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
            hotkey_msg = f'''<b>\U0001f3a4 Your New Hotkeys:</b>
\u2022 Press <b>{cfg.hotkey}</b> to hold and record (hold mode)
\u2022 Press <b>{cfg.toggle_hotkey}</b> to start/stop recording (toggle mode)'''
        else:
            hotkey_msg = f'''<b>\U0001f3a4 Your New Hotkey:</b>
\u2022 Press and hold <b>{cfg.hotkey}</b> to record (push-to-talk mode)'''

        message = Gtk.Label()
        message.set_markup(f'''<span size="large"><b>\u2705 You're All Set!</b></span>

<b>\U0001f389 Hotkeys Updated Successfully!</b>

Your new hotkeys are ready to use.

{hotkey_msg}

<b>\u23f1\ufe0f Auto-Timeout:</b>
The service will automatically stop after 5 minutes of inactivity
to conserve system resources. Just press your hotkey to wake it up!

<b>\U0001f4da Need Help?</b>
Right-click the tray icon \u2192 "Help..." for full documentation

<b>Happy dictating! \U0001f680</b>''')
        message.set_line_wrap(True)
        message.set_xalign(0)
        message.set_yalign(0)
        content.pack_start(message, True, True, 0)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.set_margin_top(10)

        ok_btn = Gtk.Button(label="Let's Go!")
        ok_btn.get_style_context().add_class("suggested-action")
        ok_btn.connect("clicked", lambda w: ready_dialog.response(Gtk.ResponseType.OK))
        button_box.pack_start(ok_btn, False, False, 0)

        content.pack_start(button_box, False, False, 0)

        ready_dialog.show_all()
        ready_dialog.run()
        ready_dialog.destroy()
        logger.info("Welcome dialog closed, continuing to main loop")

    except Exception as e:
        logger.error(f"Failed to show welcome dialog after hotkey change: {e}")


def _handle_key_event(event, mode, hold_key, toggle_key, devices, grabbed_device, cfg, input_device_idx):
    """Handle a single keyboard event. Both hold (F8) and toggle (F9) are always active.

    Returns the updated grabbed_device state (may be modified by grab/ungrab).
    """
    # --- Hold-to-talk: hold key down to record, release to stop ---
    if event.code == hold_key:
        if event.value == 1 and not state.is_recording:
            # Grab ALL keyboard devices to prevent hotkey from passing through
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
            # Ungrab BEFORE text injection so ydotool can work
            if grabbed_device:
                for ungrab_dev in grabbed_device:
                    try:
                        ungrab_dev.ungrab()
                        logger.info(f"Ungrabbed device: {ungrab_dev.name}")
                    except Exception:
                        pass
                grabbed_device = None
            stop_recording(cfg.beeps, cfg.smart_quotes, cfg.notify, cfg.language,
                           cfg.auto_space, cfg.auto_period, cfg.injection_mode)

    # --- Tap-to-toggle: press once to start, press again to stop ---
    if toggle_key and event.code == toggle_key and event.value == 1:
        if not state.is_recording:
            start_recording(cfg.beeps, cfg.notify, input_device_idx)
        else:
            stop_recording(cfg.beeps, cfg.smart_quotes, cfg.notify, cfg.language,
                           cfg.auto_space, cfg.auto_period, cfg.injection_mode)

    # --- ESC cancels in any mode ---
    if event.code == ecodes.KEY_ESC and state.is_recording and event.value == 1:
        cancel_recording(cfg.beeps, cfg.notify, "Cancelled by ESC")
        if grabbed_device:
            for ungrab_dev in grabbed_device:
                try:
                    ungrab_dev.ungrab()
                except Exception:
                    pass
            grabbed_device = None

    return grabbed_device


def _loop_evdev(cfg: Settings, input_device_idx):
    """Main event loop: monitor keyboard for hotkey presses and dispatch to recording."""
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

    # First run check: exit early if onboarding not complete
    try:
        from talktype.cuda_helper import is_first_run
        first_run = is_first_run()
    except Exception:
        first_run = False

    if first_run:
        logger.info("First run detected - onboarding not complete")
        print("Onboarding not complete. No hotkeys will be active until setup is finished.")
        return

    hold_key = _keycode_from_name(cfg.hotkey)
    toggle_key = _keycode_from_name(cfg.toggle_hotkey) if cfg.toggle_hotkey else None

    if hold_key is None:
        logger.info("No hotkey configured - service will not monitor any keys")
        print("No hotkey configured. Complete onboarding to activate dictation.")
        return

    # Show welcome dialog if user just changed hotkeys via Preferences
    from .config import get_data_dir
    welcome_flag_file = os.path.join(get_data_dir(), ".show_welcome_on_restart")
    if os.path.exists(welcome_flag_file):
        try:
            os.remove(welcome_flag_file)
            logger.info("Removed welcome flag, will show welcome dialog")
        except Exception as e:
            logger.error(f"Failed to remove welcome flag: {e}")
        _show_welcome_after_change(cfg, mode)

    # Main event loop
    grabbed_device = None
    while True:
        current_time = time.time()

        # Check for D-Bus-triggered recording commands (thread-safe via threading.Events).
        # The GLib thread sets these flags; we consume them here on the main thread.
        if _cmd_start_recording.is_set():
            _cmd_start_recording.clear()
            if not state.is_recording:
                start_recording(cfg.beeps, cfg.notify, input_device_idx)
                last_activity_time = current_time  # Reset auto-timeout

        if _cmd_stop_recording.is_set():
            _cmd_stop_recording.clear()
            if state.is_recording:
                # Must ungrab keyboard devices before stopping (same as hold-mode release)
                if grabbed_device:
                    for ungrab_dev in grabbed_device:
                        try:
                            ungrab_dev.ungrab()
                        except Exception:
                            pass
                    grabbed_device = None
                stop_recording(cfg.beeps, cfg.smart_quotes, cfg.notify, cfg.language,
                               cfg.auto_space, cfg.auto_period, cfg.injection_mode)
                last_activity_time = current_time  # Reset auto-timeout

        # Auto-timeout: shut down if no activity for configured minutes
        if timeout_enabled and not state.is_recording:
            if current_time - last_activity_time > timeout_seconds:
                print(f"\u23f0 Auto-timeout: No activity for {timeout_minutes} minutes, shutting down...")
                if cfg.notify:
                    _notify("TalkType Auto-Timeout", f"Service stopped after {timeout_minutes} minutes of inactivity")
                sys.exit(0)

        # Poll all input devices for key events
        for dev in devices:
            try:
                for event in dev.read():
                    if event.type == ecodes.EV_KEY:
                        # Reset timeout on any hotkey activity
                        if timeout_enabled and event.code in (hold_key, toggle_key, ecodes.KEY_ESC):
                            last_activity_time = current_time
                        grabbed_device = _handle_key_event(
                            event, mode, hold_key, toggle_key, devices,
                            grabbed_device, cfg, input_device_idx)
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
                        self.service_running = True
                        self.dbus_service = None

                    @property
                    def is_recording(self):
                        """Live recording state from the dictation engine."""
                        return state.is_recording

                    def show_preferences(self):
                        """Open preferences window"""
                        import subprocess
                        subprocess.Popen([sys.executable, "-m", "talktype.prefs"])

                    def start_recording(self):
                        """Signal the evdev loop to start recording (thread-safe)."""
                        if not state.is_recording:
                            _cmd_start_recording.set()

                    def stop_recording(self):
                        """Signal the evdev loop to stop recording (thread-safe)."""
                        if state.is_recording:
                            _cmd_stop_recording.set()

                    def toggle_recording(self):
                        """Toggle recording state (thread-safe)."""
                        if state.is_recording:
                            _cmd_stop_recording.set()
                        else:
                            _cmd_start_recording.set()

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
    # Register SIGUSR1 handler so the tray process can toggle recording via os.kill()
    signal.signal(signal.SIGUSR1, _handle_sigusr1)
    _loop_evdev(cfg, input_device_idx)

if __name__ == "__main__":
    main()

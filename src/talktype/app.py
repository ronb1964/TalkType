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

from typing import NamedTuple

from .normalize import normalize_text, append_auto_punct
from .config import load_config, Settings, load_custom_commands
# Imported as a module too, so the live-settings reload can read CONFIG_PATH and
# LIVE_APPLIED_KEYS without pulling each name in separately.
from . import config as config_module
from .logger import setup_logger
from .recording_indicator import RecordingIndicator
from .undo import detect_undo_command, calculate_undo_length
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

# Undo voice-command parsing/length logic lives in talktype.undo so it can
# be unit-tested without dragging in heavy audio/CUDA imports.

# D-Bus proxy for notifying the tray process of recording state changes.
# The tray owns the D-Bus name and relays signals to the GNOME extension.
_tray_dbus_proxy = None

# Every call to the tray is made from the input thread, which holds an
# exclusive grab on all keyboards while recording. dbus-python's default
# reply timeout is 25 seconds, so a busy tray — one loading a Whisper model
# on its main loop, say — froze the user's keyboard system-wide for that
# long, in every application, with no way to recover but to wait.
# These are fire-and-forget notifications: a late one is worthless anyway.
_TRAY_DBUS_TIMEOUT = 1.5

# Thread-safe recording command flags — set by signal handler or D-Bus thread, consumed by evdev loop.
# Using two separate Events (rather than one flag) so start and stop can't overwrite each other.
_cmd_start_recording = threading.Event()
_cmd_stop_recording = threading.Event()

# Hotkey test mode: when set, hotkey presses are reported via D-Bus HotkeyPressed
# signal instead of starting/stopping recording. This keeps the evdev grab alive
# and avoids XWayland phantom key-repeat floods in the Test Hotkeys dialog.
_hotkey_test_mode = threading.Event()

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

    Called from start_recording/stop_recording — that is, with every keyboard
    exclusively grabbed. It must never block for long: see _TRAY_DBUS_TIMEOUT.
    """
    try:
        import dbus
        proxy = _get_tray_dbus_proxy()
        proxy.NotifyRecordingState(
            dbus.Boolean(is_recording),
            dbus_interface='io.github.ronb1964.TalkType',
            timeout=_TRAY_DBUS_TIMEOUT,
        )
    except Exception as e:
        logger.debug(f"Could not notify tray of recording state: {e}")

def _handle_sigusr2(signum, frame):
    """SIGUSR2 = toggle hotkey test mode. Sent by the tray's prefs dialog.
    When active, hotkey presses are reported via D-Bus instead of recording.
    """
    if _hotkey_test_mode.is_set():
        _hotkey_test_mode.clear()
        print("[hotkey-test] Test mode DISABLED (SIGUSR2)", flush=True)
    else:
        _hotkey_test_mode.set()
        print("[hotkey-test] Test mode ENABLED (SIGUSR2)", flush=True)

def _get_tray_dbus_proxy():
    """Get or create the D-Bus proxy for communicating with the tray process.

    introspect=False matters: the default blocking Introspect() call is itself
    subject to the 25-second reply timeout, so building the proxy while the
    tray was busy doubled the worst-case stall to ~50s. The three methods we
    call take 'b', 's' and no arguments, all of which dbus-python infers
    correctly from the Python values, so introspection buys us nothing.
    """
    global _tray_dbus_proxy
    import dbus
    if _tray_dbus_proxy is None:
        import dbus.mainloop.glib
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        _tray_dbus_proxy = bus.get_object(
            'io.github.ronb1964.TalkType',
            '/io/github/ronb1964/TalkType',
            introspect=False,
        )
    return _tray_dbus_proxy


def _notify_tray_hotkey_pressed(key_name: str):
    """Send hotkey press notification to tray D-Bus service during test mode.

    Called from the evdev loop when _hotkey_test_mode is set. The tray's D-Bus
    service emits a HotkeyPressed signal that the prefs dialog listens for.
    """
    try:
        proxy = _get_tray_dbus_proxy()
        proxy.NotifyHotkeyPressed(
            key_name,
            dbus_interface='io.github.ronb1964.TalkType',
            timeout=_TRAY_DBUS_TIMEOUT,
        )
    except Exception as e:
        logger.debug(f"Could not notify tray of hotkey press: {e}")


def _show_voice_commands_via_dbus():
    """Tell the tray to show the voice commands quick reference via D-Bus."""
    try:
        proxy = _get_tray_dbus_proxy()
        proxy.ShowVoiceCommands(
            dbus_interface='io.github.ronb1964.TalkType',
            timeout=_TRAY_DBUS_TIMEOUT,
        )
    except Exception as e:
        logger.debug(f"Could not show voice commands via D-Bus: {e}")

# Global typing delay (set from config in main)
_typing_delay = 12  # milliseconds, default value

# Global custom commands (loaded from config in main)
_custom_commands: dict[str, str] = {}


def _expand_escapes(replacement: str) -> str:
    """Expand the two escapes the Preferences hint documents, and nothing else.

    Replacements used to be passed to re.sub as a template, which interpreted
    every backslash sequence — handy for \\n, fatal for anything else. Expanding
    these two explicitly keeps the documented line-break feature working while
    leaving a Windows path or a stray \\N as literal text.
    """
    return replacement.replace("\\n", "\n").replace("\\t", "\t")


def _command_pattern(phrase: str) -> str:
    """Build the match pattern for one trigger phrase.

    Word boundaries are applied only at ends that actually start or finish with
    a word character. A blanket \\b meant a trigger like "c++" or "#tag" could
    never match — \\b after "+" requires a following word character, so the
    phrase silently never fired despite looking configured in Preferences.
    """
    prefix = r"\b" if phrase[:1].isalnum() or phrase[:1] == "_" else ""
    suffix = r"\b" if phrase[-1:].isalnum() or phrase[-1:] == "_" else ""
    return prefix + re.escape(phrase) + suffix

def _apply_custom_commands(text: str) -> tuple[str, dict[str, str]]:
    """
    Apply user-defined custom voice commands to the transcribed text.

    Replaces spoken phrases with their configured replacements.
    Uses case-insensitive matching with word boundaries to avoid
    accidental replacements within longer words.

    If a replacement value is wrapped in double quotes (e.g. "Hello, world!"),
    the quotes are stripped and the text is protected from normalization by
    substituting a placeholder token. The caller must restore these tokens
    after normalize_text() runs.

    Args:
        text: Raw transcribed text

    Returns:
        Tuple of (processed text, protected dict mapping placeholder → literal text)
    """
    if not _custom_commands or not text:
        return text, {}

    # Longest phrase first, so "our brand customs llc" wins over the shorter
    # "our brand customs" that is also a prefix of it.
    phrases = sorted((p for p in _custom_commands if p), key=len, reverse=True)
    if not phrases:
        return text, {}

    lookup = {p.lower(): _custom_commands[p] for p in phrases}
    combined = "|".join(f"(?:{_command_pattern(p)})" for p in phrases)

    protected: dict[str, str] = {}  # placeholder → literal replacement text
    counter = 0

    def substitute(match):
        """Return the replacement for one matched phrase.

        Using a function rather than a template string is what makes a
        replacement a value instead of a pattern: re.sub does not interpret
        backslashes in what a function returns, so a Windows path or a stray
        \\N in a user's command can no longer raise and kill every dictation.
        """
        nonlocal counter
        replacement = lookup.get(match.group(0).lower())
        if replacement is None:  # pragma: no cover — every branch is in lookup
            return match.group(0)

        if len(replacement) >= 2 and replacement.startswith('"') and replacement.endswith('"'):
            # Quoted replacement — inject exactly as written, bypass normalization
            placeholder = f"§CMDLIT_{counter}§"
            counter += 1
            protected[placeholder] = replacement[1:-1]
            return placeholder

        return _expand_escapes(replacement)

    # One pass over the original text. Applying commands one after another to
    # the running result let an earlier command's output be re-scanned and
    # rewritten by a later one.
    result = re.sub(combined, substitute, text, flags=re.IGNORECASE)

    if result != text:
        logger.info(f"Custom commands applied: {text!r} -> {result!r}")

    return result, protected


def _restore_protected(text: str, protected: dict[str, str]) -> str:
    """Put quoted (literal) replacements back after normalization has run.

    Quoted commands promise the text is injected exactly as written, so a
    sentence-ending period that normalization parked directly against one is
    dropped — but only when the literal already ends in something other than a
    letter or digit. That covers a literal supplying its own punctuation
    ("Hello, world!", "Thanks.") or deliberately ending in a space ("/btw "),
    while a literal ending in a word still gets the period the user expects.
    """
    for placeholder, literal in protected.items():
        if literal and not literal[-1].isalnum():
            text = text.replace(placeholder + ".", literal)
        text = text.replace(placeholder, literal)
    return text


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
    # NOT bare "subscribe": it is an ordinary English verb, and stripping it
    # from the end of any transcription silently ate the last word of real
    # sentences ("tell them to subscribe" -> "tell them to"). It also matched
    # before the longer phrases below, so "like and subscribe" was left as
    # "like and". The multi-word forms below are what Whisper actually
    # hallucinates, and nobody dictates those.
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

# Phrases that Whisper hallucinates at the END of longer dictations.
# Only stripped when trailing real speech AND no_speech_prob is very high (>0.8),
# which means Whisper itself is uncertain the audio contained real speech.
# Kept separate from _WHOLE_TEXT_HALLUCINATION_PHRASES because the trailing
# check needs a higher confidence threshold and minimum text length to avoid
# false positives (e.g., "Sure, thank you." is real speech and should be kept).
_TRAILING_HALLUCINATION_PHRASES = [
    "thank you",
    "thank you very much",
    "thank you so much",
    "thanks",
    "you",
]


def _strip_hallucinations(text: str, no_speech_prob: float = 0.0) -> str:
    """
    Remove common Whisper hallucination phrases from transcribed text.

    Three-tier approach:
    1. YouTube-specific phrases ("thanks for watching", "like and subscribe")
       are always stripped from the end - nobody dictates these.
    2. Common words ("thank you", "bye") are only discarded when they are
       the ENTIRE transcription AND Whisper's no_speech_prob indicates
       it likely wasn't real speech. This preserves intentional dictation
       of phrases like "Thank you."
    3. Trailing hallucinations ("thank you", "you") are stripped from the
       end of longer dictations when no_speech_prob is very high (>0.8).
       This catches the common pattern where Whisper appends hallucinated
       phrases to real speech during the silence at the end of a recording.

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

    # Tier 3: Strip trailing hallucination phrases from the end of real sentences.
    # Only when: (a) no_speech_prob is very high (>0.8, Whisper is very uncertain),
    # and (b) there's substantial text before the trailing phrase (>50 chars),
    # so we don't accidentally strip real speech like "Sure, thank you."
    if text and no_speech_prob > 0.8 and len(text) > 50:
        lower_text = text.lower().rstrip(" .,!?;:")
        for phrase in _TRAILING_HALLUCINATION_PHRASES:
            if lower_text.endswith(phrase):
                phrase_start = lower_text.rfind(phrase)
                # Only strip if preceded by whitespace (segment boundary)
                if phrase_start > 0 and text[phrase_start - 1] in " \t":
                    text = text[:phrase_start].rstrip(" .,!?;:")
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

        # Feed the recording indicator whatever its active style needs.
        if recording_indicator:
            _feed_indicator(recording_indicator, indata, _spectrum_processor)

def _feed_indicator(indicator, indata, spectrum_processor):
    """Feed the recording indicator the data its active style needs.

    The RMS level is always cheap and drives the orb and the color brightness.
    Raw samples (waveform, radial) and the FFT spectrum (bars) are computed
    ONLY for the style that consumes them, so an orb user pays for no FFT.
    """
    audio = np.frombuffer(indata, dtype=np.int16).astype(np.float64)
    rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) else 0.0
    indicator.set_audio_level(min(1.0, rms / 3000.0))

    style = getattr(indicator, "style", "orb")
    if style in ("waveform", "radial"):
        indicator.set_waveform(audio.astype(np.float32) / 32768.0)
    elif style == "bars" and spectrum_processor is not None:
        indicator.set_spectrum(spectrum_processor.process(audio.astype(np.float32) / 32768.0))


# Built once when the recording indicator is created; used by _feed_indicator
# to compute the bars spectrum. None until then (and for non-bars styles).
_spectrum_processor = None


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


# Modifier key evdev codes for tracking combo hotkeys
_MODIFIER_CODES = {
    ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL,
    ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT,
    ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT,
    ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA,
}

# Map modifier names to their evdev code pairs (left + right)
_MODIFIER_NAMES = {
    "CTRL":  (ecodes.KEY_LEFTCTRL,  ecodes.KEY_RIGHTCTRL),
    "SHIFT": (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT),
    "ALT":   (ecodes.KEY_LEFTALT,   ecodes.KEY_RIGHTALT),
    "SUPER": (ecodes.KEY_LEFTMETA,  ecodes.KEY_RIGHTMETA),
}


def _parse_hotkey_combo(combo_str: str) -> tuple[set[str], int | None] | None:
    """Parse a hotkey combo string like 'Ctrl+Shift+H' into (modifier_names, keycode).

    Returns None if the string is empty or invalid.
    modifier_names is a set of uppercase modifier names (e.g. {'CTRL', 'SHIFT'}).
    keycode is the evdev keycode for the non-modifier key.
    """
    if not combo_str or not combo_str.strip():
        return None

    parts = [p.strip().upper() for p in combo_str.split("+")]
    if len(parts) < 2:
        return None  # Need at least one modifier + one key

    # Last part is the main key, everything before is a modifier
    modifiers = set()
    for part in parts[:-1]:
        if part in _MODIFIER_NAMES:
            modifiers.add(part)
        else:
            return None  # Unknown modifier

    main_key = _keycode_from_name(parts[-1])
    if main_key is None:
        return None  # Unknown key

    return (modifiers, main_key)


def _check_modifiers_held(required_mods: set[str], held_keys: set[int]) -> bool:
    """Check if all required modifiers are currently held down."""
    for mod_name in required_mods:
        left, right = _MODIFIER_NAMES[mod_name]
        if left not in held_keys and right not in held_keys:
            return False
    return True

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

# ---------------------------------------------------------------------------
# Exclusive input-device grabs
#
# While recording we take an exclusive grab on the keyboard so the hotkey
# doesn't leak through to whatever app has focus. A grab that is taken and
# never released leaves the user's keyboard dead SYSTEM-WIDE until TalkType
# exits, so the grabbed devices are tracked in module state rather than being
# threaded through return values — that way every exit path (normal stop,
# cancel, toggle, ESC, or an exception) can release them with one call.
# ---------------------------------------------------------------------------

# Devices we currently hold an exclusive grab on.
_grabbed_devices = []

# How often to look for input devices that have appeared or come back.
# Frequent enough that a reconnected keyboard starts working on its own,
# rare enough that it costs nothing in a loop running ~200 times a second.
DEVICE_RESCAN_SECONDS = 3.0

# How often to check whether the config file changed on disk. Preferences no
# longer restarts the service for settings that can be applied live, so this
# poll is what makes them take effect. One stat() per second.
CONFIG_RECHECK_SECONDS = 1.0

# mtime of the config file as of the last check. None means "not yet seen".
_last_config_mtime = None


class LiveSettings(NamedTuple):
    """Values the main loop keeps in locals and must rebind after a reload."""
    hold_key: int | None
    toggle_key: int | None
    vc_hotkey_str: str
    voice_cmds_combo: tuple | None
    voice_cmds_main_key: int | None
    mode: str


def _config_file_changed() -> bool:
    """Whether config.toml's mtime has moved since the last check.

    Returns True on the very first call once the file exists, so a service that
    starts before the file is written still picks it up. A missing or unreadable
    file is not a change — there is nothing new to apply.
    """
    global _last_config_mtime
    try:
        mtime = os.path.getmtime(config_module.CONFIG_PATH)
    except OSError:
        return False

    if mtime == _last_config_mtime:
        return False

    _last_config_mtime = mtime
    return True


def _reload_live_settings(cfg, indicator):
    """Refresh settings that can change without restarting the service.

    Updates *cfg* IN PLACE — the whole service holds a reference to that one
    object and reads most settings off it at the point of use, so refreshing
    its fields is what makes them live.

    Deliberately leaves model and device alone: those describe the WhisperModel
    that is already loaded, and rewriting them would make the config disagree
    with reality. Changing them still restarts the service.

    Returns a LiveSettings for the caller to rebind its loop locals, or None if
    the config could not be read — in which case the previous settings stay in
    force. A damaged config must never degrade a running dictation session.
    """
    try:
        fresh = load_config()
    except Exception as e:
        # Runs from a loop iterating ~200x a second; log once per change, and
        # never let anything escape into the loop.
        logger.warning(f"Could not reload settings, keeping current ones: {e}")
        return None

    try:
        for key in config_module.LIVE_APPLIED_KEYS:
            if hasattr(fresh, key) and hasattr(cfg, key):
                setattr(cfg, key, getattr(fresh, key))

        global _typing_delay
        _typing_delay = getattr(cfg, "typing_delay", 12)

        if indicator is not None:
            indicator.apply_settings(
                cfg.indicator_position,
                cfg.indicator_size,
                cfg.indicator_offset_x,
                cfg.indicator_offset_y,
                style=cfg.indicator_style,
                color_mode=cfg.indicator_color_mode,
                custom_color=cfg.indicator_color,
                backing=cfg.indicator_backing,
                sensitivity=cfg.indicator_sensitivity,
            )

        vc_hotkey_str = getattr(cfg, "voice_commands_hotkey", "")
        voice_cmds_combo = _parse_hotkey_combo(vc_hotkey_str)

        return LiveSettings(
            hold_key=_keycode_from_name(cfg.hotkey),
            toggle_key=_keycode_from_name(cfg.toggle_hotkey) if cfg.toggle_hotkey else None,
            vc_hotkey_str=vc_hotkey_str,
            voice_cmds_combo=voice_cmds_combo,
            voice_cmds_main_key=voice_cmds_combo[1] if voice_cmds_combo else None,
            mode=cfg.mode.lower().strip(),
        )
    except Exception as e:
        logger.warning(f"Could not apply reloaded settings: {e}", exc_info=True)
        return None

# Letter keys, used to tell a real keyboard from a device that merely reports
# key events (power buttons, lid switches, mouse buttons, consumer-control nodes).
# Built by name, not as a numeric range: evdev codes follow the physical
# scancode order of a PC keyboard, so KEY_A..KEY_Z spans the home row and
# several punctuation keys while leaving KEY_M outside it entirely.
_LETTER_KEYS = frozenset(
    getattr(ecodes, f"KEY_{letter}") for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)


def _is_keyboard_device(dev) -> bool:
    """True if *dev* can deliver the hotkey and is therefore worth grabbing.

    Grabbing everything under /dev/input also captures mice, touchpads, audio
    jacks and the power button, freezing the pointer for the whole recording.

    Two capability checks, in this order:

    1. It must report letter keys. Power buttons, lid switches, audio jacks and
       consumer-control nodes report none, so this drops them immediately.
    2. It must not be a pointing device. Logitech Unifying receivers advertise a
       superset HID descriptor, so a wireless mouse claims all 26 letter keys
       and all 12 F-keys just like a keyboard does. What separates them is real
       pointer motion (REL_X) combined with mouse buttons — the same test
       libinput uses. This also excludes ydotoold's virtual device, which is how
       TalkType types and must never be grabbed.

    Note the check is REL_X specifically, not the EV_REL event type: the K800
    keyboard declares EV_REL while exposing no motion axis, so testing the type
    alone would throw out a real keyboard and let the hotkey leak through.
    """
    try:
        caps = dev.capabilities()
    except Exception:
        return False

    keys = set(caps.get(ecodes.EV_KEY) or [])
    if sum(1 for k in keys if k in _LETTER_KEYS) < 3:
        return False

    rel_axes = set(caps.get(ecodes.EV_REL) or [])
    is_pointer = ecodes.REL_X in rel_axes and ecodes.BTN_LEFT in keys
    return not is_pointer


def _grab_all_devices(devices) -> None:
    """Take an exclusive grab on each device, tracking the ones that succeed.

    Devices that refuse the grab (permissions, already grabbed) are skipped and
    left untracked so we never try to release something we don't hold.
    """
    for dev in devices:
        try:
            dev.grab()
            _grabbed_devices.append(dev)
            logger.info(f"Grabbed device: {dev.name}")
        except Exception as e:
            logger.warning(f"Could not grab {getattr(dev, 'name', dev)}: {e}")


def _release_all_grabs() -> None:
    """Release every grab we hold. Idempotent, and safe to call from any path.

    One unplugged device must not strand the grabs on every other keyboard, so
    each release is attempted independently and the registry is always cleared.
    """
    global _grabbed_devices
    for dev in _grabbed_devices:
        try:
            dev.ungrab()
            logger.info(f"Ungrabbed device: {getattr(dev, 'name', dev)}")
        except Exception as e:
            logger.warning(f"Could not ungrab {getattr(dev, 'name', dev)}: {e}")
    _grabbed_devices = []


def _rediscover_devices(devices) -> int:
    """Add keyboards that have appeared since the last scan. Returns how many.

    Devices were enumerated once at startup and never again, so a device
    dropped by _drop_dead_devices — after a wireless receiver blip, a USB
    reset or a resume from suspend — was gone for the life of the process.
    On a single-keyboard machine that means the hotkey silently stops working
    until TalkType is restarted, with only a log line the user never sees.

    Matched on the device node path, which is what identifies a device across
    reconnects here. Non-keyboards are ignored so this never grows the poll
    list with mice or power buttons.
    """
    known = {getattr(d, "path", None) for d in devices}
    added = 0
    for path in list_devices():
        if path in known:
            continue
        try:
            dev = InputDevice(path)
            if not _is_keyboard_device(dev):
                continue
            try:
                dev.set_nonblocking(True)
            except Exception:
                pass
            devices.append(dev)
            added += 1
            logger.info(f"Input device appeared, now monitoring: {dev.name}")
        except Exception as e:
            # A node we cannot open (permissions, disappeared mid-scan) must
            # not stop the rest of the scan.
            logger.debug(f"Could not open {path}: {e}")
    return added


def _drop_dead_devices(dead_devices, devices, mode, cfg) -> None:
    """Remove input devices that failed mid-read, ending a recording we could
    no longer end any other way.

    In hold mode the key-up that stops recording can only come from the device
    the key was pressed on. If that device dies — a wireless receiver blip, a
    USB reset, a resume from suspend — the release event is unreachable and
    state.is_recording would stay True for the life of the process.

    That matters far more than the lost device: both the stranded-grab
    backstop and the auto-timeout are gated on `not state.is_recording`, so a
    stuck flag leaves every *other* keyboard exclusively grabbed indefinitely
    and stops the service ever timing out. The user cannot type anywhere, and
    the only way back is the tray. So: end the recording deliberately.
    """
    if not dead_devices:
        return

    for dev in dead_devices:
        if dev in devices:
            devices.remove(dev)

    if state.is_recording and mode == "hold":
        logger.warning(
            "Input device died while the hold hotkey was down — ending the "
            "recording, since its key-up can no longer arrive"
        )
        _release_all_grabs()
        stop_recording(cfg.beeps, cfg.smart_quotes, cfg.notify, cfg.language,
                       cfg.auto_space, cfg.auto_period, cfg.injection_mode)

    dead_devices.clear()


def _release_grabs_if_not_recording() -> bool:
    """Safety net: holding an exclusive grab while not recording is always a bug.

    Called once per event-loop pass so that any path which fails to release —
    including one added later — self-heals within milliseconds instead of
    leaving the user with a dead keyboard. Returns True if it had to recover.
    """
    if _grabbed_devices and not state.is_recording:
        logger.warning(f"Releasing {len(_grabbed_devices)} stranded input grab(s)")
        _release_all_grabs()
        return True
    return False


def _open_input_stream(device_idx) -> None:
    """Open and start the microphone stream. Raises if the device is unusable."""
    # Use the device's native sample rate (may differ from 16kHz on ALSA hw: devices)
    state.recording_samplerate = _get_device_samplerate(device_idx)
    sd.default.channels = CHANNELS
    sd.default.samplerate = state.recording_samplerate
    state.stream = sd.InputStream(callback=_sd_callback, dtype='int16', device=device_idx)
    state.stream.start()


def start_recording(beeps_on: bool, notify_on: bool, input_device_idx) -> bool:
    """Begin capturing audio. Returns True only if recording actually started.

    On failure this releases any input-device grabs before returning. The
    keyboard is grabbed just before this is called, so without that release a
    microphone error would leave the user unable to type anywhere at all.
    """
    state.frames = []
    state.was_cancelled = False
    state.press_t0 = time.time()
    # Set before the stream starts — _sd_callback drops frames unless it's set.
    state.is_recording = True
    try:
        _open_input_stream(input_device_idx)
    except Exception as first_error:
        # The mic is stored as a device NUMBER, resolved once at startup. Unplug
        # a USB device and the numbering shifts, leaving that number pointing at
        # nothing. Re-resolve by name and try once more before giving up.
        logger.warning(f"Microphone {input_device_idx} failed ({first_error}); re-resolving")
        _stop_stream_safely()
        try:
            fresh_idx = _pick_input_device(load_config().mic)
            _open_input_stream(fresh_idx)
            logger.info(f"Microphone re-resolved to device {fresh_idx}")
        except Exception as e:
            # Genuinely unavailable: unplugged, or held exclusively by another
            # app. Undo everything and tell the user — failing silently here is
            # what left the keyboard grabbed and the machine unusable.
            logger.error(f"Could not start recording: {e}", exc_info=True)
            print(f"⚠️  Could not start recording: {e}")
            state.is_recording = False
            _stop_stream_safely()
            _release_all_grabs()
            _beep(beeps_on, *CANCEL_BEEP)
            if notify_on:
                _notify("TalkType", "Microphone unavailable — check that no other app is using it")
            return False

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

    return True

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

def _is_wayland_session() -> bool:
    """True when a Wayland compositor is available for wl-copy to talk to."""
    return bool(os.environ.get("WAYLAND_DISPLAY"))


# ydotool talks to ydotoold over a socket. These calls run on the same thread
# that polls for the hotkey, so an untimed call against a wedged daemon stops
# dictation responding at all, with the tray still showing the service as up.
YDOTOOL_TIMEOUT_S = 5.0


def _ydotool_key(keys, timeout: float = YDOTOOL_TIMEOUT_S, what: str = "keystroke") -> bool:
    """Send raw key codes via ydotool. True only if they were actually delivered.

    ydotool exits non-zero when it can't reach ydotoold ("Please check if
    ydotoold is running"). That result used to be discarded with check=False, so
    keystrokes that never happened were reported as success — which is how text
    ended up in the undo buffer that the document had never received.
    """
    if not _which("ydotool"):
        return False
    try:
        result = subprocess.run(
            ["ydotool", "key"] + list(keys),
            check=False, env=_get_ydotool_env(),
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.error(f"ydotool {what} timed out after {timeout}s — is ydotoold wedged?")
        return False
    except Exception as e:
        logger.debug(f"ydotool {what} failed: {e}")
        return False

    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        logger.error(f"ydotool {what} failed (exit {result.returncode}): {detail}")
        return False
    return True


def _send_shift_enter():
    """Send Shift+Enter keystrokes to create line break without submitting."""
    # KEY_LEFTSHIFT (42), KEY_ENTER (28)
    return _ydotool_key(["42:1", "28:1", "28:0", "42:0"], what="shift+enter")

def _send_enter():
    """Send Enter keystroke to create a new line."""
    # KEY_ENTER (28)
    return _ydotool_key(["28:1", "28:0"], what="enter")

def _send_select_all_delete():
    """Send Ctrl+A then Backspace to clear the entire input field.

    Used by the 'delete everything' voice command — wipes the whole textarea
    regardless of whether the contents came from TalkType, manual typing, or
    pasting from elsewhere.
    """
    # KEY_LEFTCTRL (29) + KEY_A (30), then KEY_BACKSPACE (14)
    if not _ydotool_key(["29:1", "30:1", "30:0", "29:0"], what="select-all"):
        return False
    time.sleep(0.05)
    return _ydotool_key(["14:1", "14:0"], what="delete")

def _type_text(text: str) -> bool:
    """Type text (handling line-break markers). Returns True if it was
    actually typed into the focused app, False if injection failed."""
    # Handle special markers first
    if "§SHIFT_ENTER§" in text:
        ok = True
        parts = text.split("§SHIFT_ENTER§")
        for i, part in enumerate(parts):
            if part:  # Type the text part
                if not _type_text_raw(part):
                    ok = False
            if i < len(parts) - 1:  # Not the last part, send Shift+Enter
                time.sleep(0.05)  # Small delay between text and key
                # The line break is part of the text. Dropping this return
                # value reported a partial injection as a complete one, and
                # the undo buffer then held one character more than the
                # document had — so "undo that" ate into the user's own text.
                if not _send_shift_enter():
                    ok = False
                time.sleep(0.05)  # Small delay after key
        return ok

    # Handle regular newlines by converting them to Enter key presses
    if "\n" in text:
        ok = True
        parts = text.split("\n")
        for i, part in enumerate(parts):
            if part:  # Type the text part
                if not _type_text_raw(part):
                    ok = False
            if i < len(parts) - 1:  # Not the last part, send Enter
                time.sleep(0.05)  # Small delay between text and key
                if not _send_enter():
                    ok = False
                time.sleep(0.05)  # Small delay after key
        return ok

    # Normal text typing
    return _type_text_raw(text)

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
            try:
                stdout, stderr = proc.communicate(input=text.encode("utf-8"), timeout=20)
            except subprocess.TimeoutExpired:
                # Kill and reap the hung ydotool so it doesn't linger and keep
                # typing into whatever is focused later.
                proc.kill()
                proc.communicate()
                logger.error("ydotool type timed out after 20s; killed the process")
                return False
            if proc.returncode != 0:
                logger.error(f"ydotool type failed: rc={proc.returncode}, stderr={stderr.decode()}")
                return False
            logger.info(f"ydotool type succeeded: rc=0, typed {len(text)} chars")
            return True
        except Exception as e:
            logger.debug(f"ydotool failed: {e}")
    if _which("wtype"):
        # Report wtype's real exit code so the undo buffer only tracks text
        # that was actually typed (consistent with the ydotool branch above).
        wt = subprocess.run(["wtype", "--", text], check=False)
        return wt.returncode == 0
    if _which("wl-copy"):
        try:
            import pyperclip
            pyperclip.copy(text)
            print("📋 Copied to clipboard. Ctrl+V to paste.")
            logger.info("Text copied to clipboard (fallback mode)")
            # Nothing was actually typed into the field — report failure so
            # the undo buffer doesn't track text the user must paste manually.
            return False
        except Exception:
            pass
    logger.error("Could not type text: no ydotool/wtype/wl-copy available")
    print("⚠️  Could not type text (no ydotool/wtype).")
    return False

# Window classes that need Ctrl+Shift+V for paste (terminals).
# All other apps get plain Ctrl+V — works in chat/editor/browser inputs and
# avoids a Chromium/Electron regression that mishandles synthetic Ctrl+Shift+V.
_TERMINAL_WM_CLASSES = frozenset({
    "org.gnome.Ptyxis", "Ptyxis",
    "org.gnome.Terminal", "Gnome-terminal",
    "konsole", "org.kde.konsole",
    "kitty",
    "Alacritty",
    "WezTerm", "org.wezfurlong.wezterm",
    "foot", "footclient",
    "Tilix", "com.gexperts.Tilix",
    "Terminator",
    "xterm", "XTerm", "UXTerm",
    "rxvt", "URxvt",
})

# Electron/Chromium apps where synthetic paste (Ctrl+V via ydotool) is broken
# on Wayland — modifier-key chords from /dev/uinput are silently dropped and
# the focused input blurs. For these apps, route to a fast Type path instead
# (plain character keystrokes still work, per OpenWhispr #240 and others).
_ELECTRON_PASTE_BROKEN_CLASSES = frozenset({
    "Claude", "claude", "claude-desktop", "Claude Desktop", "anthropic-claude",
})


def _query_focused_window_class() -> str | None:
    """Query the tray's D-Bus service for the currently focused window's wm_class.

    The dictation engine (this process) is a *subprocess* of the tray, so its
    own in-memory `_focused_window_class` is always None. The tray owns the
    D-Bus service and receives push updates from the GNOME extension; we ask
    it across processes via a fast D-Bus call.

    Returns the wm_class string, or None if unknown / D-Bus unavailable.
    """
    try:
        # Shared, cached, introspect-free proxy — this used to build a fresh
        # one on every paste, paying a blocking Introspect() each time, and
        # neither call carried a timeout. Both waits are 25s by default, on
        # the thread between the user releasing the hotkey and their text
        # appearing. This is only a hint for choosing the paste shortcut, so
        # a slow answer is worth less than a fast "don't know".
        proxy = _get_tray_dbus_proxy()
        result = proxy.GetFocusedWindowClass(
            dbus_interface="io.github.ronb1964.TalkType",
            timeout=_TRAY_DBUS_TIMEOUT,
        )
        s = str(result) if result else ""
        return s if s else None
    except Exception as e:
        logger.debug(f"Focused window class query failed: {e}")
        return None


def _type_text_fast(text: str, delay_ms: int = 1):
    """Type text via ydotool with a very small inter-event delay.

    Used for Electron/Chromium apps where clipboard-paste is broken on Wayland.
    1ms per event is the practical floor — ~415 chars/sec, ~3x faster than
    the older 3ms default. Going lower risks Electron's input buffer dropping
    characters under burst.
    """
    if not _which("ydotool"):
        logger.error("Fast-type fallback: ydotool unavailable")
        return False
    try:
        env = _get_ydotool_env()
        d = str(max(1, delay_ms))
        logger.info(f"ydotool fast-type: delay={d}ms, text_len={len(text)}")
        proc = subprocess.Popen(
            ["ydotool", "type", "-d", d, "-H", d, "-f", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env,
        )
        try:
            _stdout, stderr = proc.communicate(input=text.encode("utf-8"), timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            logger.error("ydotool fast-type timed out after 30s; killed the process")
            return False
        if proc.returncode != 0:
            logger.error(f"ydotool fast-type failed: rc={proc.returncode}, stderr={stderr.decode(errors='replace')}")
            return False
        return True
    except Exception as e:
        logger.error(f"Fast-type exception: {e}")
        return False


def _paste_text(text: str, send_trailing_keys: bool = False):
    """
    Wayland paste injection: put text on clipboard, then Ctrl+V or Shift+Ctrl+V.
    
    Automatically detects terminal applications and uses Shift+Ctrl+V for them,
    regular Ctrl+V for everything else.

    Returns True only when the text actually reached the focused app. Reporting
    success unconditionally caused two silent failures: on a session where the
    clipboard was never set, Ctrl+V pasted whatever the user had copied earlier;
    and text that never landed was still recorded in the undo buffer, so a later
    "undo that" backspaced over the user's own writing.

    Args:
        text: Text to paste (should NOT contain §SHIFT_ENTER§ markers)
        send_trailing_keys: If True, send additional key presses after paste
    """
    # wl-copy talks to a Wayland compositor. On an X11 login it fails instantly,
    # and firing Ctrl+V anyway pastes the previous clipboard contents.
    if not _is_wayland_session():
        logger.info("Paste unavailable: not a Wayland session — falling back to typing")
        return False

    try:
        if _which("wl-copy") and _which("ydotool"):
            # Pick paste keystroke from focused window's wm_class:
            #   - terminals need Ctrl+Shift+V (Ctrl+V is the bash literal-char escape)
            #   - everything else uses plain Ctrl+V (the canonical paste shortcut,
            #     and avoids an Electron regression that mishandles synthetic
            #     Ctrl+Shift+V — drops focus on the input).
            # wm_class is pushed by the GNOME extension on every focus change.

            # Copy text to clipboard
            # wl-copy needs to stay running to serve clipboard requests
            paste_start = time.time()
            logger.info(f"TIMING: Starting paste operation for {len(text)} chars")
            proc = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                proc.stdin.write(text.encode("utf-8"))
                proc.stdin.close()
                wl_copy_time = time.time() - paste_start
                logger.info(f"TIMING: wl-copy started in {wl_copy_time:.3f}s")

                # Wait for clipboard to be ready (needs time for wl-copy to set up)
                time.sleep(0.08)

                # wl-copy forks on success, so the process we spawned exits 0
                # right away; a still-running one is serving the clipboard and
                # is equally healthy. A non-zero exit means the clipboard was
                # never set, and pasting now would insert the wrong text.
                status = proc.poll()
                if status is not None and status != 0:
                    logger.error(f"wl-copy failed (exit {status}) — clipboard not set, skipping paste")
                    return False

                # Resolve focused window class via D-Bus query (tray-side cache).
                # None when the extension hasn't pushed yet or the service is down.
                focused_class = _query_focused_window_class()

                is_terminal = focused_class in _TERMINAL_WM_CLASSES if focused_class else False

                # KEY_LEFTSHIFT=42, KEY_LEFTCTRL=29, KEY_V=47
                if is_terminal:
                    keys = ["42:1", "29:1", "47:1", "47:0", "29:0", "42:0"]  # Ctrl+Shift+V
                    logger.info(f"Paste: Ctrl+Shift+V (terminal class={focused_class!r})")
                else:
                    keys = ["29:1", "47:1", "47:0", "29:0"]  # Ctrl+V
                    logger.info(f"Paste: Ctrl+V (class={focused_class!r})")

                ydotool_start = time.time()
                if not _ydotool_key(keys, what="paste"):
                    # The keystroke never reached the compositor: the text is
                    # sitting on the clipboard but never made it into the app.
                    logger.error("Paste keystroke failed — text was not inserted")
                    return False
                ydotool_time = time.time() - ydotool_start
                logger.info(f"TIMING: ydotool paste command took {ydotool_time:.3f}s")

                # Brief delay for paste to register
                time.sleep(0.05)
                total_paste_time = time.time() - paste_start
                logger.info(f"TIMING: Total paste operation time: {total_paste_time:.3f}s")
                return True
            finally:
                # Always reap wl-copy, even if the paste raised partway, so it
                # never lingers as an orphan holding the clipboard open.
                try:
                    proc.terminate()
                    proc.wait(timeout=0.3)
                except Exception:
                    pass  # wl-copy cleanup is best-effort
    except subprocess.TimeoutExpired as e:
        logger.error(f"Paste injection timeout: {e}")
    except Exception as e:
        logger.error(f"Paste injection failed: {e}")
        pass
    return False

def _press_space():
    # Inject a literal Space keypress via ydotool when possible; fallback to typing a space
    # KEY_SPACE = 57
    if _ydotool_key(["57:1", "57:0"], what="space"):
        return
    if _which("wtype"):
        subprocess.run(["wtype", "--", " "], check=False, timeout=YDOTOOL_TIMEOUT_S); return

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

def _send_backspaces(count: int) -> bool:
    """Send *count* backspace keypresses. True only if they were delivered.

    The caller updates the undo buffer from this result, so a wrong answer here
    desynchronises the buffer from the document and the next undo eats the
    user's own writing.
    """
    if count <= 0:
        return True
    # KEY_BACKSPACE = 14, pressed and released once per character. A long undo
    # is thousands of events, so the timeout scales with the work requested.
    key_sequence = []
    for _ in range(count):
        key_sequence.extend(["14:1", "14:0"])
    timeout = max(YDOTOOL_TIMEOUT_S, count * 0.02)
    return _ydotool_key(key_sequence, timeout=timeout, what=f"{count} backspaces")

def _transcribe_audio(audio_f32, language: str | None) -> str | None:
    """Run Whisper transcription on audio and filter hallucinations.

    Returns the raw transcribed text, or None if no speech was detected.
    """
    transcribe_start = time.time()
    segments, _ = model.transcribe(
        audio_f32,
        vad_filter=False,
        beam_size=5,
        condition_on_previous_text=True,
        temperature=0.0,
        # Word-level timestamps strengthen Whisper's long-form seek logic,
        # preventing dropped words at pause boundaries (the v0.5.17 fix —
        # replaces the old without_timestamps=True footgun).
        word_timestamps=True,
        # Repetition-loop guards: Whisper can get stuck repeating one phrase
        # many times in a row. A mild penalty plus n-gram blocking breaks
        # the loop without changing normal decoding.
        repetition_penalty=1.1,
        no_repeat_ngram_size=5,
        language=(language or None),
        # vad_filter is disabled: Silero VAD trims speech onsets at segment
        # boundaries (especially the start of recordings and after sentence
        # pauses), causing leading words to vanish from raw Whisper output.
        # See: github.com/SYSTRAN/faster-whisper/issues/925
        # Push-to-talk dictation has minimal non-speech audio to filter,
        # so disabling VAD has near-zero quality cost.
        # hallucination_silence_threshold also stays unset — same reason:
        # it drops real speech after natural 2+ second pauses. Trailing
        # hallucination phrases are handled by _strip_hallucinations().
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
    detected = detect_undo_command(raw)
    if not detected:
        return False

    undo_type, count = detected
    label = undo_type if count == 1 else f"{count} {undo_type}s"
    logger.info(f"Undo command detected: {label}")
    print(f"\U0001f519 Undo command: {label}")

    # 'everything' clears the entire input field via Ctrl+A + Backspace.
    # No tracked dictation required \u2014 wipes whatever is in the textarea,
    # including text that wasn't typed by TalkType.
    if undo_type == 'everything':
        if _send_select_all_delete():
            state.last_inserted_text = ""
            state.continue_mid_sentence = False
            _beep(beeps_on, *READY_BEEP)
            if notify_on: _notify("TalkType", "Cleared input field")
        else:
            print("\u26a0\ufe0f  Could not clear input field (ydotool unavailable)")
            _beep(beeps_on, *CANCEL_BEEP)
            if notify_on: _notify("TalkType", "Could not clear field")
        return True

    if not state.last_inserted_text:
        print("\u2139\ufe0f  Nothing to undo (no previous dictation)")
        logger.info("Undo requested but no previous text to undo")
        _beep(beeps_on, *CANCEL_BEEP)
        if notify_on: _notify("TalkType", "Nothing to undo")
        return True

    # Calculate how many characters to delete (iterates `count` times)
    delete_count = calculate_undo_length(state.last_inserted_text, undo_type, count)
    logger.info(f"Undo: deleting {delete_count} characters (last text was {len(state.last_inserted_text)} chars, count={count})")
    print(f"\U0001f519 Undoing {delete_count} characters ({label})")

    if delete_count > 0:
        # Only shrink the buffer once the deletion is confirmed. Assuming it
        # worked meant TalkType played the success beep while nothing had been
        # deleted, leaving the buffer out of step with the document — so the
        # next undo backspaced over text the user had typed themselves.
        if not _send_backspaces(delete_count):
            print("⚠️  Undo failed — nothing was deleted")
            logger.error("Undo failed: backspaces were not delivered; buffer left unchanged")
            _beep(beeps_on, *CANCEL_BEEP)
            if notify_on:
                _notify("TalkType", "Undo failed — check that ydotool is running")
            return True

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
        if notify_on: _notify("TalkType", f"Undid last {label}")
    else:
        print("\u2139\ufe0f  Nothing to undo for this scope")
        _beep(beeps_on, *CANCEL_BEEP)
    return True


def _safe_to_lowercase_first_word(text: str) -> bool:
    """True when the leading capital is Whisper's sentence-start capital and
    nothing more, so undoing it is safe.

    Two kinds of word are capitalized for reasons that have nothing to do with
    where the sentence begins, and lowercasing them corrupts real text:

      * the pronoun "I" (and I'm / I'll / I've / I'd), which became "i"
      * acronyms, where only the first letter was touched: "NASA" -> "nASA"

    Proper nouns like "Ron" are genuinely ambiguous — Whisper capitalizes them
    both as names and as sentence starts — so they are left alone here and
    remain a known limitation rather than a guess.
    """
    first = text.split(maxsplit=1)[0] if text.split() else ""
    if not first:
        return False

    # The pronoun "I", bare or contracted.
    stripped = first.rstrip(".,;:!?")
    if stripped == "I" or stripped.startswith("I'"):
        return False

    # Acronyms: more than one capital and no lowercase letters ("NASA", "USA").
    letters = [c for c in stripped if c.isalpha()]
    if len(letters) > 1 and all(c.isupper() for c in letters):
        return False

    return True


def _prepare_text(raw: str, smart_quotes: bool, auto_period: bool, auto_space: bool) -> str:
    """Apply voice commands, normalize, handle mid-sentence, add auto-period/space.

    Returns the final text string ready for injection.
    """
    # Apply custom voice commands (phrase → replacement)
    # Quoted replacements come back as placeholder tokens in `protected`
    processed, protected = _apply_custom_commands(raw)

    # Normalize text (capitalization, punctuation, etc.). auto_period is passed
    # through because this pass ends every line with a full stop of its own \u2014
    # without it the preference was dead, since append_auto_punct below only
    # ever saw text that had already been given a period.
    text = normalize_text(
        processed if smart_quotes else processed.replace("\u201c","\"").replace("\u201d","\""),
        auto_period=auto_period,
    )

    # Restore quoted (literal) custom command replacements before any further
    # processing so that auto-period/space checks see the real final text.
    text = _restore_protected(text, protected)

    # Handle mid-sentence continuation after undo:
    # lowercase the first letter if we're continuing a sentence
    if state.continue_mid_sentence and text:
        if text[0].isupper() and _safe_to_lowercase_first_word(text):
            text = text[0].lower() + text[1:]
            logger.info("Lowercased first letter for mid-sentence continuation")
        state.continue_mid_sentence = False

    # Auto-period and auto-space. When the utterance ends with a line-break
    # command, the period lands BEFORE the break and no trailing space is
    # added (previously "hello new line" left an orphan ". " on the next line).
    text = append_auto_punct(text, auto_period, auto_space)
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

    # Electron-paste-broken override: if the focused window is an Electron app
    # where synthetic Ctrl+V silently fails on Wayland, skip clipboard-paste and
    # use fast direct typing instead. Only kicks in for auto/paste — if the user
    # explicitly chose "type", we already use Type mode.
    if injection_mode != "type":
        focused_class = _query_focused_window_class()
        logger.info(f"Electron-broken check: focused_class={focused_class!r}")
        if focused_class in _ELECTRON_PASTE_BROKEN_CLASSES:
            logger.info(f"Electron-paste-broken override: class={focused_class!r}, using fast-type")
            print(f"⌨️  Electron app ({focused_class}): using fast-type fallback")

            # Split on §SHIFT_ENTER§ (line-break voice command) and \n so
            # we send actual Shift+Enter keystrokes between text chunks
            # instead of typing the marker literally.
            # Tab characters (from the "tab" voice command) are converted to
            # 4 spaces here: a real Tab keypress moves focus from Claude Desktop's
            # chat textarea to the Send button, and the next typed space then
            # activates it — submitting the message mid-dictation.
            marker = "\xa7SHIFT_ENTER\xa7"
            unified = text.replace("\n", marker) if "\n" in text else text
            unified = unified.replace("\t", "    ")
            success = True
            delivered_parts = 0  # chunks confirmed in the document
            if marker in unified:
                parts = unified.split(marker)
                for i, part in enumerate(parts):
                    if part and not _type_text_fast(part):
                        success = False
                        break
                    delivered_parts = i + 1
                    if i < len(parts) - 1:
                        time.sleep(0.03)
                        if not _send_shift_enter():
                            success = False
                            break
                        time.sleep(0.03)
            else:
                success = _type_text_fast(unified)
                delivered_parts = 1 if success else 0

            if success:
                injection_time = time.time() - injection_start
                logger.info(f"TIMING: Fast-type injection completed in {injection_time:.2f}s")
                logger.info(f"Text injected via fast-type: {len(text)} chars in {injection_time:.2f}s")
                # Track injected text for undo. Store the typed form: tabs
                # already replaced with 4 spaces, and each line-break marker
                # as one '\n' (one Shift+Enter keystroke = one backspace),
                # so backspace counts match what was actually sent.
                state.last_inserted_text = unified.replace(marker, "\n")
                logger.debug(f"Stored last inserted text for undo: {len(state.last_inserted_text)} chars (fast-type)")
                return

            # Partial delivery: chunks already in the document must not be sent
            # again by the fallback below, or the user gets a duplicate copy.
            if delivered_parts:
                landed = marker.join(unified.split(marker)[:delivered_parts])
                state.last_inserted_text = landed.replace(marker, "\n")
                logger.warning(
                    f"Fast-type stopped after {delivered_parts} chunk(s) — "
                    f"not re-injecting, undo buffer holds only what landed"
                )
                return
            # Nothing landed, so the normal injection path can safely try again.
            logger.warning("Fast-type failed, falling through to normal injection")

    use_paste = (actual_mode == "paste")
    logger.info(f"Injection mode: configured={injection_mode!r}, actual={actual_mode!r}, atspi={use_atspi}, reason={reason}")
    if injection_mode == "auto":
        print(f"\U0001f50d Auto mode: {reason}")

    # Tracks whether text actually reached the focused app. Only a confirmed
    # injection updates the undo buffer \u2014 otherwise a later "undo last word"
    # would backspace characters the user's document never received.
    inject_ok = True

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
                inject_ok = _type_text(text)
        except Exception as e:
            logger.error(f"AT-SPI insertion error: {e}")
            print("\u26a0\ufe0f  AT-SPI error, falling back to typing")
            inject_ok = _type_text(text)

    # --- Smart hybrid paste (text with line-break markers) ---
    elif use_paste and ("\xa7SHIFT_ENTER\xa7" in text or "\n" in text):
        marker = "\xa7SHIFT_ENTER\xa7"
        logger.info("Smart hybrid mode: splitting text on markers")
        parts = text.split(marker)
        logger.info(f"Split into {len(parts)} parts")

        # Track where delivery stopped. Falling back by re-injecting the whole
        # text left the document with the chunks that already landed followed by
        # a complete second copy of everything, which undo could not clean up.
        resume_at = None
        needs_break = False
        for i, part in enumerate(parts):
            if part:
                logger.info(f"Pasting part {i+1}/{len(parts)}: {len(part)} chars")
                if not _paste_text(part):
                    logger.warning(f"Paste failed on part {i+1}; will type the remainder")
                    resume_at = i
                    break
                time.sleep(0.08)
            if i < len(parts) - 1:
                logger.info(f"Sending Shift+Enter after part {i+1}")
                if not _send_shift_enter():
                    # The chunk landed but its line break didn't \u2014 resume from
                    # the next chunk and supply the missing break.
                    logger.warning(f"Line break failed after part {i+1}; will type the remainder")
                    resume_at, needs_break = i + 1, True
                    break
                time.sleep(0.05)

        if resume_at is None:
            print(f"\u2702\ufe0f  Inject (smart paste) {len(parts)} chunks, {len(text)} total chars")
            logger.info(f"Smart hybrid paste completed: {len(parts)} chunks")
        else:
            remainder = (marker if needs_break else "") + marker.join(parts[resume_at:])
            print(f"\u2328\ufe0f  Inject (type) remainder len={len(remainder)} [paste failed partway]")
            if _type_text(remainder):
                inject_ok = True  # delivered chunks + typed remainder == full text
            else:
                # Only the chunks before the failure reached the document. Record
                # exactly those, so undo can't delete what was never inserted.
                delivered = marker.join(parts[:resume_at])
                state.last_inserted_text = delivered.replace(marker, "\n")
                logger.warning(
                    f"Injection stopped after {resume_at}/{len(parts)} chunks \u2014 "
                    f"undo buffer holds only what landed"
                )
                return

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
        inject_ok = _type_text(text)
        injection_time = time.time() - injection_start
        logger.info(f"TIMING: Typing injection completed in {injection_time:.2f}s")
        logger.info(f"Text injected via typing: {len(text)} chars in {injection_time:.2f}s")
        if injection_time > 1.0:
            logger.warning(f"Typing injection slow: {injection_time:.2f}s")

    # Track injected text for undo — but ONLY when injection actually
    # succeeded. Line-break markers are stored as '\n' (one keystroke on
    # screen = one character in the buffer) so undo backspace counts stay in
    # sync with what was typed. If injection failed, leave the previous
    # buffer untouched so undo can't delete text the document never got.
    if inject_ok:
        state.last_inserted_text = text.replace("\xa7SHIFT_ENTER\xa7", "\n")
        logger.debug(f"Stored last inserted text for undo: {len(state.last_inserted_text)} chars")
    else:
        logger.warning("Injection failed — undo buffer left unchanged")


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
        _ellipsis = "\u2026"  # Must be outside f-string for Python 3.10 compat
        if notify_on: _notify("TalkType", f"Transcribed: {text[:80]}{_ellipsis if len(text)>80 else ''}")

        # Stage 4: Inject text into the active application
        if text:
            _inject_text(text, injection_mode, t0)

    except Exception as e:
        logger.error(f"Transcription error: {e}", exc_info=True)
        print(f"\u274c Transcription error: {e}")
        _beep(beeps_on, *READY_BEEP)
        _ellipsis = "\u2026"  # Must be outside f-string for Python 3.10 compat
        if notify_on: _notify("TalkType", f"Transcription failed: {str(e)[:60]}{_ellipsis if len(str(e))>60 else ''}")

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


def _handle_key_event(event, mode, hold_key, toggle_key,
                      voice_cmds_combo, held_modifiers,
                      devices, cfg, input_device_idx):
    """Handle a single keyboard event. Both hold (F8) and toggle (F9) are always active.

    Grabbed devices are tracked in module state (see _grab_all_devices), not
    returned, so that every way recording can end — release, toggle, ESC, or an
    exception inside start_recording — releases the keyboard.
    """
    # --- Hotkey test mode: report presses via D-Bus instead of recording ---
    if _hotkey_test_mode.is_set() and event.value == 1:
        key_name = None
        if event.code == hold_key:
            key_name = "hold"
        elif toggle_key and event.code == toggle_key:
            key_name = "toggle"
        if key_name:
            _notify_tray_hotkey_pressed(key_name)
        return  # Don't process hotkeys normally in test mode

    # --- Voice Commands combo hotkey (e.g. Ctrl+Shift+H) ---
    if voice_cmds_combo and event.value == 1:
        required_mods, main_key = voice_cmds_combo
        if event.code == main_key and _check_modifiers_held(required_mods, held_modifiers):
            # Briefly grab the keyboards to stop the keypress leaking into the
            # focused app. Three things this used to get wrong, all of which
            # the recording path already had right:
            #   - it grabbed EVERY device, so the pointer froze too;
            #   - it tracked them in a local list, invisible to
            #     _release_all_grabs() and the stranded-grab backstop;
            #   - an exception from the tray call skipped the ungrab entirely,
            #     stranding the grabs with no way to recover them.
            # Same helpers as recording, and a finally that always releases.
            _grab_all_devices([d for d in devices if _is_keyboard_device(d)])
            try:
                _show_voice_commands_via_dbus()
            finally:
                _release_all_grabs()
            return

    # --- Hold-to-talk: hold key down to record, release to stop ---
    if event.code == hold_key:
        if event.value == 1 and not state.is_recording:
            # Grab the keyboards so the hotkey doesn't reach the focused app.
            # start_recording releases them itself if the mic fails to open.
            _grab_all_devices([d for d in devices if _is_keyboard_device(d)])
            start_recording(cfg.beeps, cfg.notify, input_device_idx)
        elif event.value == 0 and state.is_recording:
            # Ungrab BEFORE text injection so ydotool can work
            _release_all_grabs()
            stop_recording(cfg.beeps, cfg.smart_quotes, cfg.notify, cfg.language,
                           cfg.auto_space, cfg.auto_period, cfg.injection_mode)

    # --- Tap-to-toggle: press once to start, press again to stop ---
    if toggle_key and event.code == toggle_key and event.value == 1:
        if not state.is_recording:
            start_recording(cfg.beeps, cfg.notify, input_device_idx)
        else:
            # Also reached by brushing the toggle key mid-hold. Release first,
            # or the hold key's release branch is skipped and the grab is stranded.
            _release_all_grabs()
            stop_recording(cfg.beeps, cfg.smart_quotes, cfg.notify, cfg.language,
                           cfg.auto_space, cfg.auto_period, cfg.injection_mode)

    # --- ESC cancels in any mode ---
    if event.code == ecodes.KEY_ESC and state.is_recording and event.value == 1:
        cancel_recording(cfg.beeps, cfg.notify, "Cancelled by ESC")
        _release_all_grabs()


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
    last_device_scan = time.time()
    last_config_check = time.time()
    # Establish the config's current mtime so the first poll does not report a
    # spurious change and re-apply settings the service just started with.
    _config_file_changed()

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

    # Voice commands hotkey supports combos like "Ctrl+Shift+H"
    vc_hotkey_str = getattr(cfg, 'voice_commands_hotkey', '')
    voice_cmds_combo = _parse_hotkey_combo(vc_hotkey_str)
    voice_cmds_main_key = voice_cmds_combo[1] if voice_cmds_combo else None

    if hold_key is None:
        logger.info("No hotkey configured - service will not monitor any keys")
        print("No hotkey configured. Complete onboarding to activate dictation.")
        return

    if voice_cmds_combo:
        print(f"Voice Commands hotkey: {vc_hotkey_str}")
        logger.info(f"Voice Commands hotkey: {vc_hotkey_str}")

    # Track which modifier keys are currently held (for combo detection)
    held_modifiers: set[int] = set()

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
    dead_devices = []
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
                _release_all_grabs()
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
                        # Track modifier key state for combo detection
                        if event.code in _MODIFIER_CODES:
                            if event.value in (1, 2):  # press or repeat
                                held_modifiers.add(event.code)
                            elif event.value == 0:  # release
                                held_modifiers.discard(event.code)

                        # Reset timeout on any hotkey activity
                        if timeout_enabled and event.code in (hold_key, toggle_key, ecodes.KEY_ESC, voice_cmds_main_key):
                            last_activity_time = current_time
                        _handle_key_event(
                            event, mode, hold_key, toggle_key,
                            voice_cmds_combo, held_modifiers,
                            devices, cfg, input_device_idx)
            except BlockingIOError:
                pass
            except OSError as e:
                # Device unplugged or suspended mid-read. Drop it so we stop
                # polling a dead handle, but keep serving the others.
                logger.warning(f"Input device {getattr(dev, 'name', dev)} failed, dropping it: {e}")
                dead_devices.append(dev)
            except Exception as e:
                # Never swallow silently: an unlogged exception here is what
                # turned a microphone error into an unexplained keyboard lockup.
                logger.error(f"Error handling input event: {e}", exc_info=True)

        _drop_dead_devices(dead_devices, devices, mode, cfg)

        # Pick up keyboards that have (re)appeared. Only while idle: rescanning
        # mid-recording would add an ungrabbed device to a grabbed set, letting
        # the hotkey leak into the focused app. Throttled because it stats
        # every node under /dev/input and this loop runs ~200x a second.
        if not state.is_recording and current_time - last_device_scan >= DEVICE_RESCAN_SECONDS:
            last_device_scan = current_time
            _rediscover_devices(devices)

        # Pick up settings changed in Preferences without restarting. Only
        # while idle: rebinding the hotkey mid-recording would leave the
        # release of the old key unmatched, stranding a device grab. Settings
        # that need the model rebuilt (model, device) still force a restart —
        # see config.LIVE_APPLIED_KEYS.
        if not state.is_recording and current_time - last_config_check >= CONFIG_RECHECK_SECONDS:
            last_config_check = current_time
            if _config_file_changed():
                live = _reload_live_settings(cfg, recording_indicator)
                if live is not None:
                    hold_key = live.hold_key
                    toggle_key = live.toggle_key
                    vc_hotkey_str = live.vc_hotkey_str
                    voice_cmds_combo = live.voice_cmds_combo
                    voice_cmds_main_key = live.voice_cmds_main_key
                    mode = live.mode
                    logger.info("Applied settings change without restarting")

        # Backstop: we must never hold a keyboard grab while not recording.
        _release_grabs_if_not_recording()

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
                # Fall back to CPU — skip confirmation dialog since the user already
                # chose this model via the preset; a surprise dialog in a background
                # process would block silently and cause the service to hang.
                model = download_model_with_progress(
                    settings.model,
                    device="cpu",
                    compute_type="int8",
                    show_confirmation=False
                )

                if model is None:
                    raise Exception("Model download cancelled by user")

                print("✅ Model loaded successfully on CPU (fallback)")
                logger.info("Model loaded on CPU (fallback from CUDA)")

                # Persist device=cpu to config so future service restarts don't
                # try CUDA again and crash in a loop.
                try:
                    from .config import load_config, save_config
                    _cfg = load_config()
                    if _cfg.device == "cuda":
                        _cfg.device = "cpu"
                        save_config(_cfg)
                        logger.info("Updated config: device=cpu (CUDA unavailable — preventing crash loop)")
                except Exception as _ce:
                    logger.warning(f"Could not persist device=cpu after CUDA fallback: {_ce}")

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

    # Guard: large-v3 requires CUDA — silently fall back to medium if CUDA
    # is not installed. This prevents the service from becoming completely
    # non-functional when someone opens the app without CUDA after having
    # previously configured it with the large model.
    if cfg.model == "large-v3":
        try:
            from .cuda_helper import has_talktype_cuda_libraries
            if not has_talktype_cuda_libraries():
                logger.warning(
                    "large-v3 selected but CUDA libraries not found — "
                    "falling back to 'medium' to prevent non-functional state."
                )
                print("⚠️  large-v3 requires CUDA (not installed). Falling back to 'medium'.")
                cfg.model = "medium"
        except Exception:
            pass  # If cuda_helper unavailable, let the existing error handling deal with it

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
                        """Change the Whisper model (requires service restart).

                        Writes through config.save_config, the same path every
                        other writer uses. This used to hand-roll JSON into
                        ~/.config/talktype/settings.json — a file this app has
                        never read or written; the real settings are TOML at
                        ~/.config/TalkType/config.toml. The change therefore
                        landed nowhere and was gone by the restart it asked
                        the user to perform.
                        """
                        try:
                            from .config import VALID_MODELS, load_config, save_config

                            if model_name not in VALID_MODELS:
                                logger.error(
                                    f"SetModel: refusing unknown model {model_name!r}"
                                )
                                return

                            cfg = load_config()
                            cfg.model = model_name
                            save_config(cfg)
                            self.config.model = model_name

                            logger.info(f"Model changed to {model_name} (restart required)")

                            # Emit signal so extension updates
                            if self.dbus_service:
                                self.dbus_service.emit_model_changed(model_name)
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
                        size=cfg.indicator_size,
                        style=cfg.indicator_style,
                        color_mode=cfg.indicator_color_mode,
                        custom_color=cfg.indicator_color,
                        backing=cfg.indicator_backing,
                        sensitivity=cfg.indicator_sensitivity,
                    )
                    # Spectrum processor for the bars style; _feed_indicator uses it.
                    global _spectrum_processor
                    from .indicator_dsp import SpectrumProcessor
                    _spectrum_processor = SpectrumProcessor(bins=20)
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
    # Register signal handlers:
    # SIGUSR1: toggle recording (sent by tray for D-Bus toggle commands)
    # SIGUSR2: toggle hotkey test mode (sent by prefs dialog for Test Hotkeys)
    signal.signal(signal.SIGUSR1, _handle_sigusr1)
    signal.signal(signal.SIGUSR2, _handle_sigusr2)
    _loop_evdev(cfg, input_device_idx)

if __name__ == "__main__":
    main()

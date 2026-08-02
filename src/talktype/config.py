from __future__ import annotations
import os
import logging
import shutil
import subprocess
import time
try:
    import tomllib  # Python 3.11+
    _USE_TOMLLIB = True  # tomllib requires binary mode ("rb")
except ImportError:
    import toml as tomllib  # Python 3.10 fallback
    _USE_TOMLLIB = False  # toml library requires text mode ("r")
from dataclasses import dataclass, fields
import sys

logger = logging.getLogger(__name__)

# Detect dev mode - use separate paths for dev vs production
DEV_MODE = os.environ.get("DEV_MODE") == "1"
CONFIG_DIR = "talktype-dev" if DEV_MODE else "talktype"
DATA_DIR = "TalkType-dev" if DEV_MODE else "TalkType"

CONFIG_PATH = os.path.expanduser(f"~/.config/{CONFIG_DIR}/config.toml")


class ConfigError(Exception):
    """One or more settings hold values the app cannot use.

    Carries the individual problems so a caller can show the user which setting
    is wrong instead of just failing.
    """

    def __init__(self, errors, fields=None):
        self.errors = list(errors)
        self.fields = list(fields or [])
        super().__init__("; ".join(self.errors))

    def report(self) -> str:
        """Human-readable summary, suitable for stderr or a dialog."""
        lines = ["Configuration validation failed:"]
        lines += [f"  • {e}" for e in self.errors]
        lines.append(f"\nPlease fix your configuration in: {CONFIG_PATH}")
        lines.append("Or use environment variables (DICTATE_MODEL, DICTATE_DEVICE, etc.)")
        return "\n".join(lines)

# ---------------------------------------------------------------------------
# Validation constants — defined once, used by validate_config()
# ---------------------------------------------------------------------------

VALID_MODELS = {
    "tiny", "tiny.en",
    "base", "base.en",
    "small", "small.en",
    "medium", "medium.en",
    "large", "large-v1", "large-v2", "large-v3",
}

VALID_DEVICES = {"cpu", "cuda"}
VALID_MODES = {"hold", "toggle"}
VALID_INJECTION_MODES = {"type", "paste", "auto"}

VALID_INDICATOR_POSITIONS = {
    "center", "top-left", "top-center", "top-right",
    "bottom-left", "bottom-center", "bottom-right",
    "left-center", "right-center",
}

VALID_INDICATOR_SIZES = {"small", "medium", "large"}


@dataclass
class Settings:
    model: str = "small"        # tiny/base/small/medium/large-v3 …
    device: str = "cpu"         # "cpu" or "cuda"
    hotkey: str = ""            # hold-to-talk hotkey (empty until user picks during onboarding)
    beeps: bool = True          # beeps on/off
    smart_quotes: bool = True   # "smart quotes"
    mode: str = "hold"          # "hold" or "toggle"
    toggle_hotkey: str = ""     # used only when mode="toggle" (empty until user picks during onboarding)
    mic: str = ""               # substring to match input device (empty = default)
    notify: bool = False        # desktop notifications
    language: str = ""          # optional language code (e.g., "en"); empty = auto-detect
    auto_space: bool = True     # prepend a space before new utterance when not starting a new line/tab
    auto_period: bool = True   # append a period when an utterance ends without terminal punctuation
    paste_injection: bool = False  # when adding a leading space is unreliable, paste " ␣text" via clipboard
    injection_mode: str = "auto"  # "auto" (smart detection), "type" (ydotool/wtype), or "paste" (wl-copy + Ctrl+V)
    typing_delay: int = 12  # milliseconds between keystrokes when typing (5-50, higher = slower but more reliable)
    auto_timeout_enabled: bool = True   # enable automatic timeout after inactivity (default: on)
    auto_timeout_minutes: int = 5       # minutes of inactivity before auto-stop
    recording_indicator: bool = True    # show visual recording indicator near cursor
    indicator_position: str = "center"  # screen position: center, top-left, top-center, top-right, bottom-left, bottom-center, bottom-right, left-center, right-center
    indicator_offset_x: int = 0         # custom X offset from position anchor (pixels, can be negative)
    indicator_offset_y: int = 0         # custom Y offset from position anchor (pixels, can be negative)
    indicator_size: str = "medium"      # indicator size: small, medium, large
    voice_commands_hotkey: str = "Ctrl+Alt+V"  # hotkey combo to open voice commands quick reference
    auto_check_updates: bool = True      # automatically check for updates on startup (once per day)
    last_update_check: str = ""          # ISO timestamp of last update check
    language_mode: str = "auto"          # "auto" (detect language) or "manual" (use `language`); UI state for prefs
    launch_at_login: bool = False        # start TalkType automatically at login (prefs manages the autostart file)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_toml_file(path: str) -> dict:
    """Load a TOML file and return its data as a dict. Returns {} on failure."""
    file_mode = "rb" if _USE_TOMLLIB else "r"
    with open(path, file_mode) as f:
        return tomllib.load(f)

def _env_bool(key: str, default: bool) -> bool:
    """Read a boolean from an environment variable, falling back to *default*.

    Treats "0", "false", "off", "no" (case-insensitive) as False;
    anything else as True.
    """
    val = os.getenv(key)
    if val is None:
        return default
    return val.lower() not in {"0", "false", "off", "no"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validation_problems(s: Settings) -> list[tuple[str, str]]:
    """Return (field name, message) for every setting holding an unusable value.

    Naming the field, not just the message, lets a caller repair that one
    setting instead of discarding the whole configuration.
    """
    problems = []

    if s.model not in VALID_MODELS:
        problems.append(("model", f"Invalid model '{s.model}'. Valid options: {', '.join(sorted(VALID_MODELS))}"))

    if s.device.lower() not in VALID_DEVICES:
        problems.append(("device", f"Invalid device '{s.device}'. Must be 'cpu' or 'cuda'"))

    if s.mode.lower() not in VALID_MODES:
        problems.append(("mode", f"Invalid mode '{s.mode}'. Must be 'hold' or 'toggle'"))

    if s.injection_mode.lower() not in VALID_INJECTION_MODES:
        problems.append(("injection_mode", f"Invalid injection_mode '{s.injection_mode}'. Must be 'type', 'paste', or 'auto'"))

    if s.auto_timeout_minutes <= 0:
        problems.append(("auto_timeout_minutes", f"Invalid auto_timeout_minutes '{s.auto_timeout_minutes}'. Must be positive"))

    if s.indicator_position.lower() not in VALID_INDICATOR_POSITIONS:
        problems.append(("indicator_position", f"Invalid indicator_position '{s.indicator_position}'. Valid options: {', '.join(sorted(VALID_INDICATOR_POSITIONS))}"))

    if s.indicator_size.lower() not in VALID_INDICATOR_SIZES:
        problems.append(("indicator_size", f"Invalid indicator_size '{s.indicator_size}'. Valid options: {', '.join(sorted(VALID_INDICATOR_SIZES))}"))

    return problems


def validate_config(s: Settings) -> None:
    """Raise ConfigError if any setting holds a value the app cannot use.

    Raises rather than exits. This runs inside load_config(), which the tray
    calls once per second \u2014 calling sys.exit() here made the tray icon
    disappear from the panel within a second of a bad value being saved, with
    no dialog and nothing to indicate which setting was at fault. SystemExit
    also deliberately bypasses `except Exception`, so the tray's own error
    handling could not catch it either.
    """
    problems = _validation_problems(s)
    if problems:
        raise ConfigError([msg for _, msg in problems],
                          fields=[name for name, _ in problems])


def _repair_invalid_fields(s: Settings, error: ConfigError) -> Settings:
    """Reset only the settings that are unusable, keeping everything else.

    One bad value should cost the user that one setting, not their whole
    configuration and not a working tray icon.
    """
    defaults = Settings()
    for name in error.fields:
        default = getattr(defaults, name)
        logger.warning(f"Resetting invalid setting {name!r} to default {default!r}")
        setattr(s, name, default)

    if not getattr(load_config, "_invalid_reported", False):
        print("\u26a0\ufe0f  Some settings held invalid values and were reset to defaults:", file=sys.stderr)
        for message in error.errors:
            print(f"  \u2022 {message}", file=sys.stderr)
        load_config._invalid_reported = True

    return s


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

# Type casters for dataclass fields — maps annotation strings to builtins.
# Needed because `from __future__ import annotations` stores types as strings.
_TYPE_CASTERS = {"str": str, "bool": bool, "int": int}


# Config cache — avoids re-reading TOML from disk when file hasn't changed.
# The tray polls load_config() every 1 second; this reduces disk I/O to near zero.
_config_cache = None
_config_mtime = 0.0

def _recover_damaged_config(error: Exception) -> Settings:
    """Set a damaged config aside and recover the last known good settings.

    Returns the recovered Settings — from the .bak written by the previous
    successful save when one exists, otherwise defaults.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    quarantine = f"{CONFIG_PATH}.corrupt-{stamp}"
    try:
        shutil.copy2(CONFIG_PATH, quarantine)
        logger.error(f"Damaged config saved to {quarantine}: {error}")
        print(f"⚠️  Settings file was unreadable ({error}).", file=sys.stderr)
        print(f"    A copy was kept at: {quarantine}", file=sys.stderr)
    except OSError as copy_error:
        logger.error(f"Could not preserve damaged config: {copy_error}")

    backup = f"{CONFIG_PATH}.bak"
    if os.path.exists(backup):
        try:
            data = _load_toml_file(backup)
            if data:
                recovered = Settings()
                for fld in fields(recovered):
                    if fld.name in data:
                        cast = _TYPE_CASTERS.get(fld.type, str)
                        setattr(recovered, fld.name, cast(data[fld.name]))
                logger.info(f"Recovered settings from {backup}")
                print("    Your previous settings were restored from backup.", file=sys.stderr)
                return recovered
        except Exception as restore_error:
            logger.error(f"Backup at {backup} is also unreadable: {restore_error}")

    print("    Settings have been reset to defaults.", file=sys.stderr)
    return Settings()


def load_config() -> Settings:
    global _config_cache, _config_mtime

    # Return cached config if the file hasn't been modified
    try:
        current_mtime = os.path.getmtime(CONFIG_PATH)
        if _config_cache is not None and current_mtime == _config_mtime:
            return _config_cache
        _config_mtime = current_mtime
    except OSError:
        # File doesn't exist yet — return cache if we have one
        if _config_cache is not None:
            return _config_cache

    s = Settings()
    if os.path.exists(CONFIG_PATH):
        try:
            data = _load_toml_file(CONFIG_PATH)
            # An existing file with nothing in it is damage, not configuration:
            # empty parses as valid TOML, so it silently produced all-defaults \u2014
            # including a blank hotkey, which kills dictation with no message.
            if not data:
                raise ValueError("config file is empty")
            # Apply TOML values using dataclass field types for casting
            for fld in fields(s):
                if fld.name in data:
                    cast = _TYPE_CASTERS.get(fld.type, str)
                    setattr(s, fld.name, cast(data[fld.name]))
        except Exception as e:
            # Preserve the damaged file and fall back to the last known good
            # settings. Silently resetting to defaults looked like a fresh
            # install, and the next save overwrote the user's real settings for
            # good.
            s = _recover_damaged_config(e)

    # Environment variable overrides
    s.model = os.getenv("DICTATE_MODEL", s.model)
    s.device = os.getenv("DICTATE_DEVICE", s.device)
    s.hotkey = os.getenv("DICTATE_HOTKEY", s.hotkey)
    s.mode = os.getenv("DICTATE_MODE", s.mode)
    s.toggle_hotkey = os.getenv("DICTATE_TOGGLE_HOTKEY", s.toggle_hotkey)
    s.mic = os.getenv("DICTATE_MIC", s.mic)
    s.language = os.getenv("DICTATE_LANGUAGE", s.language)
    s.injection_mode = os.getenv("DICTATE_INJECTION_MODE", s.injection_mode)

    # Boolean environment overrides
    s.auto_space = _env_bool("DICTATE_AUTO_SPACE", s.auto_space)
    s.auto_period = _env_bool("DICTATE_AUTO_PERIOD", s.auto_period)
    s.paste_injection = _env_bool("DICTATE_PASTE_INJECTION", s.paste_injection)
    s.beeps = _env_bool("DICTATE_BEEPS", s.beeps)
    s.smart_quotes = _env_bool("DICTATE_SMART_QUOTES", s.smart_quotes)
    s.notify = _env_bool("DICTATE_NOTIFY", s.notify)
    s.auto_timeout_enabled = _env_bool("DICTATE_AUTO_TIMEOUT_ENABLED", s.auto_timeout_enabled)

    # Integer environment override
    timeout_minutes = os.getenv("DICTATE_AUTO_TIMEOUT_MINUTES")
    if timeout_minutes is not None:
        s.auto_timeout_minutes = int(timeout_minutes)

    try:
        validate_config(s)
    except ConfigError as e:
        # Keep the process alive. The tray polls this once a second, so a single
        # bad value must cost the user that setting, not their tray icon.
        s = _repair_invalid_fields(s, e)

    _config_cache = s
    return s


def _toml_value(val) -> str:
    """Format a Python value as a TOML literal."""
    if isinstance(val, bool):
        return str(val).lower()     # true / false
    if isinstance(val, int):
        return str(val)             # bare integer
    return f'"{val}"'               # quoted string


def _toml_string(value: str) -> str:
    """Quote and escape *value* as a TOML basic string."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def write_text_atomic(path: str, text: str, keep_backup: bool = True) -> None:
    """Replace *path* with *text* without ever leaving it half-written.

    The previous version was opened in truncate mode, so an interruption —
    most realistically a full disk, which this app can cause itself by
    downloading multi-gigabyte models — left the file empty every time. On the
    next launch every setting fell back to its default, including the hotkey,
    which defaults to blank and silently kills dictation.

    Writing to a sibling temp file and renaming is atomic on POSIX: readers see
    either the old file or the new one, never a partial one. The fsync before
    the rename is what makes that hold across a power loss rather than just a
    crash.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)

    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())

        if keep_backup and os.path.exists(path):
            try:
                shutil.copy2(path, f"{path}.bak")
            except OSError as e:
                # A backup is a bonus, not a precondition for saving.
                logger.warning(f"Could not back up {path}: {e}")

        os.replace(tmp_path, path)
    except BaseException:
        # Never leave a stray temp file behind on failure.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def save_config(s: Settings) -> None:
    """Save Settings to TOML file.

    Uses dataclass introspection so new fields are automatically included.
    """
    lines = ["# TalkType config"]
    for fld in fields(s):
        lines.append(f"{fld.name} = {_toml_value(getattr(s, fld.name))}")
    write_text_atomic(CONFIG_PATH, "\n".join(lines) + "\n")


def merge_changed_keys(original: dict, current: dict, base: dict) -> dict:
    """Overlay only the keys that changed between *original* and *current*
    onto *base*, returning base.

    Used by the Preferences window to avoid clobbering settings another
    process (the tray) wrote while the window was open: *original* is the
    config as loaded when the window opened, *current* is the UI state at
    save time, and *base* is a fresh read of the file on disk. Keys the
    user didn't touch keep their on-disk values; keys the user changed win.
    """
    for key, value in current.items():
        if key not in original or original[key] != value:
            base[key] = value
    return base


def get_data_dir():
    """
    Get the data directory path based on dev mode.

    Returns:
        str: Path to ~/.local/share/TalkType (production) or ~/.local/share/TalkType-dev (dev mode)
    """
    return os.path.expanduser(f"~/.local/share/{DATA_DIR}")


# ---------------------------------------------------------------------------
# Audio device detection
# ---------------------------------------------------------------------------

def find_input_device(mic_substring: str | None) -> int | None:
    """Find the best input device index for recording.

    When mic_substring is set, finds a device whose name contains it.
    When empty/None, auto-detects the system's default microphone via
    PipeWire (wpctl) instead of relying on PortAudio's ALSA default,
    which can return garbage audio on PipeWire systems with virtual
    128-channel default devices.

    Returns:
        Device index for sounddevice, or None to use sounddevice's default.
    """
    try:
        import sounddevice as sd
        q = sd.query_devices()
    except Exception:
        return None

    # --- User specified a mic name — find it by substring match ---
    if mic_substring:
        m = mic_substring.lower()
        candidates = [
            (i, d) for i, d in enumerate(q)
            if d.get("max_input_channels", 0) > 0
            and m in d.get("name", "").lower()
        ]
        if candidates:
            return candidates[0][0]
        return None  # Not found — fall back to sounddevice default

    # --- No mic configured — auto-detect the real default source ---
    # PipeWire's ALSA "default" device (128 channels) can return clipped
    # garbage audio instead of actual mic input. We ask PipeWire directly
    # for the real default source name, then match it in sounddevice's list.
    try:
        result = subprocess.run(
            ["wpctl", "inspect", "@DEFAULT_SOURCE@"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                stripped = line.strip()
                # Look for node.nick (short name) or node.description (full name)
                if "node.nick" in stripped or "node.description" in stripped:
                    parts = stripped.split("=", 1)
                    if len(parts) == 2:
                        source_name = parts[1].strip().strip('"').strip()
                        if not source_name:
                            continue
                        # Find this device in sounddevice's list, skipping
                        # virtual devices with unrealistically many channels
                        for i, d in enumerate(q):
                            if (d.get("max_input_channels", 0) > 0
                                    and d.get("max_input_channels", 0) < 10
                                    and source_name.lower()
                                    in d.get("name", "").lower()):
                                logger.info(
                                    f"Auto-detected mic: [{i}] {d['name']}"
                                    " (via PipeWire default source)")
                                print(f"🎙️  Auto-detected mic: {d['name']}")
                                return i
    except FileNotFoundError:
        pass  # wpctl not installed — not a PipeWire system
    except Exception:
        pass

    # --- Fallback: pick a real hardware mic, avoiding virtual devices ---
    # Filter out monitors, virtual sinks, and PipeWire wrappers
    skip_names = {"monitor", "default", "pipewire", "sysdefault", "spdif"}
    hw_mics = [
        (i, d) for i, d in enumerate(q)
        if d.get("max_input_channels", 0) > 0
        and d.get("max_input_channels", 0) < 10
        and not any(s in d.get("name", "").lower() for s in skip_names)
    ]
    if hw_mics:
        # Prefer USB mics (external) over built-in analog
        usb = [(i, d) for i, d in hw_mics
               if "usb" in d.get("name", "").lower()]
        chosen_i, chosen_d = (usb or hw_mics)[0]
        logger.info(
            f"Auto-detected mic (hardware fallback):"
            f" [{chosen_i}] {chosen_d['name']}")
        print(f"🎙️  Auto-detected mic: {chosen_d['name']}")
        return chosen_i

    return None  # Last resort: let sounddevice use its own default


# Custom voice commands configuration
CUSTOM_COMMANDS_PATH = os.path.expanduser(f"~/.config/{CONFIG_DIR}/custom_commands.toml")

def load_custom_commands() -> dict[str, str]:
    """
    Load custom voice commands from TOML file.

    Returns:
        dict: Mapping of spoken phrases to replacement text
              e.g., {"my email": "user@example.com", "signature": "Best regards,\\nRon"}
    """
    commands = {}
    if os.path.exists(CUSTOM_COMMANDS_PATH):
        try:
            data = _load_toml_file(CUSTOM_COMMANDS_PATH)
            commands = dict(data.get("commands", {}))
        except Exception as e:
            print(f"Warning: Could not load custom commands: {e}")
    return commands

def save_custom_commands(commands: dict[str, str]) -> None:
    """
    Save custom voice commands to TOML file.

    Args:
        commands: Dictionary mapping spoken phrases to replacement text
    """
    lines = [
        "# TalkType Custom Voice Commands",
        '# Format: "spoken phrase" = "replacement text"',
        "# Use \\n for line breaks in replacements",
        "",
        "[commands]",
    ]
    for phrase, replacement in commands.items():
        # Escape BOTH sides. Only the replacement used to be escaped, so a
        # phrase containing a double quote produced a malformed line that made
        # the whole file unparseable — every custom command stopped working at
        # once, and Preferences then showed an empty list and saved it back,
        # deleting the lot.
        lines.append(f'{_toml_string(phrase)} = {_toml_string(replacement)}')

    write_text_atomic(CUSTOM_COMMANDS_PATH, "\n".join(lines) + "\n")

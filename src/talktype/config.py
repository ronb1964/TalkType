from __future__ import annotations
import os
import logging
import subprocess
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
    auto_check_updates: bool = True      # automatically check for updates on startup (once per day)
    last_update_check: str = ""          # ISO timestamp of last update check


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

def validate_config(s: Settings) -> None:
    """
    Validate configuration settings and exit with clear error message if invalid.
    """
    errors = []

    if s.model not in VALID_MODELS:
        errors.append(f"Invalid model '{s.model}'. Valid options: {', '.join(sorted(VALID_MODELS))}")

    if s.device.lower() not in VALID_DEVICES:
        errors.append(f"Invalid device '{s.device}'. Must be 'cpu' or 'cuda'")

    if s.mode.lower() not in VALID_MODES:
        errors.append(f"Invalid mode '{s.mode}'. Must be 'hold' or 'toggle'")

    if s.injection_mode.lower() not in VALID_INJECTION_MODES:
        errors.append(f"Invalid injection_mode '{s.injection_mode}'. Must be 'type', 'paste', or 'auto'")

    if s.auto_timeout_minutes <= 0:
        errors.append(f"Invalid auto_timeout_minutes '{s.auto_timeout_minutes}'. Must be positive")

    if s.indicator_position.lower() not in VALID_INDICATOR_POSITIONS:
        errors.append(f"Invalid indicator_position '{s.indicator_position}'. Valid options: {', '.join(sorted(VALID_INDICATOR_POSITIONS))}")

    if s.indicator_size.lower() not in VALID_INDICATOR_SIZES:
        errors.append(f"Invalid indicator_size '{s.indicator_size}'. Valid options: {', '.join(sorted(VALID_INDICATOR_SIZES))}")

    if errors:
        print("\u274c Configuration validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  \u2022 {error}", file=sys.stderr)
        print(f"\nPlease fix your configuration in: {CONFIG_PATH}", file=sys.stderr)
        print("Or use environment variables (DICTATE_MODEL, DICTATE_DEVICE, etc.)", file=sys.stderr)
        sys.exit(1)


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
            # Apply TOML values using dataclass field types for casting
            for fld in fields(s):
                if fld.name in data:
                    cast = _TYPE_CASTERS.get(fld.type, str)
                    setattr(s, fld.name, cast(data[fld.name]))
        except Exception as e:
            if not getattr(load_config, '_error_printed', False):
                print(f"\u26a0\ufe0f  Error loading config from {CONFIG_PATH}: {e}", file=sys.stderr)
                load_config._error_printed = True

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

    validate_config(s)
    _config_cache = s
    return s


def _toml_value(val) -> str:
    """Format a Python value as a TOML literal."""
    if isinstance(val, bool):
        return str(val).lower()     # true / false
    if isinstance(val, int):
        return str(val)             # bare integer
    return f'"{val}"'               # quoted string


def save_config(s: Settings) -> None:
    """Save Settings to TOML file.

    Uses dataclass introspection so new fields are automatically included.
    """
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        f.write("# TalkType config\n")
        for fld in fields(s):
            f.write(f"{fld.name} = {_toml_value(getattr(s, fld.name))}\n")


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
    os.makedirs(os.path.dirname(CUSTOM_COMMANDS_PATH), exist_ok=True)
    with open(CUSTOM_COMMANDS_PATH, "w") as f:
        f.write("# TalkType Custom Voice Commands\n")
        f.write("# Format: \"spoken phrase\" = \"replacement text\"\n")
        f.write("# Use \\n for line breaks in replacements\n\n")
        f.write("[commands]\n")
        for phrase, replacement in commands.items():
            escaped_replacement = replacement.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            f.write(f'"{phrase}" = "{escaped_replacement}"\n')

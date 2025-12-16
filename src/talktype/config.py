from __future__ import annotations
import os
try:
    import tomllib  # Python 3.11+
    _USE_TOMLLIB = True  # tomllib requires binary mode ("rb")
except ImportError:
    import toml as tomllib  # Python 3.10 fallback
    _USE_TOMLLIB = False  # toml library requires text mode ("r")
from dataclasses import dataclass
import sys

# Detect dev mode - use separate paths for dev vs production
DEV_MODE = os.environ.get("DEV_MODE") == "1"
CONFIG_DIR = "talktype-dev" if DEV_MODE else "talktype"
DATA_DIR = "TalkType-dev" if DEV_MODE else "TalkType"

CONFIG_PATH = os.path.expanduser(f"~/.config/{CONFIG_DIR}/config.toml")

@dataclass
class Settings:
    model: str = "small"        # tiny/base/small/medium/large-v3 …
    device: str = "cpu"         # "cpu" or "cuda"
    hotkey: str = "F8"          # hold-to-talk hotkey
    beeps: bool = True          # beeps on/off
    smart_quotes: bool = True   # "smart quotes"
    mode: str = "hold"          # "hold" or "toggle"
    toggle_hotkey: str = "F9"   # used only when mode="toggle"
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

def validate_config(s: Settings) -> None:
    """
    Validate configuration settings and exit with clear error message if invalid.

    Checks:
    - model: valid Whisper model name
    - device: "cpu" or "cuda"
    - mode: "hold" or "toggle"
    - auto_timeout_minutes: positive integer
    - injection_mode: "type", "paste", or "auto"
    - hotkey/toggle_hotkey: reasonable key names (basic validation)
    """
    errors = []

    # Valid Whisper model names
    valid_models = {
        "tiny", "tiny.en",
        "base", "base.en",
        "small", "small.en",
        "medium", "medium.en",
        "large", "large-v1", "large-v2", "large-v3"
    }
    if s.model not in valid_models:
        errors.append(f"Invalid model '{s.model}'. Valid options: {', '.join(sorted(valid_models))}")

    # Valid device
    if s.device.lower() not in {"cpu", "cuda"}:
        errors.append(f"Invalid device '{s.device}'. Must be 'cpu' or 'cuda'")

    # Valid mode
    if s.mode.lower() not in {"hold", "toggle"}:
        errors.append(f"Invalid mode '{s.mode}'. Must be 'hold' or 'toggle'")

    # Valid injection mode
    if s.injection_mode.lower() not in {"type", "paste", "auto"}:
        errors.append(f"Invalid injection_mode '{s.injection_mode}'. Must be 'type', 'paste', or 'auto'")

    # Auto-timeout minutes must be positive
    if s.auto_timeout_minutes <= 0:
        errors.append(f"Invalid auto_timeout_minutes '{s.auto_timeout_minutes}'. Must be positive")

    # Basic hotkey validation - just check it's not empty and looks reasonable
    if not s.hotkey or len(s.hotkey.strip()) == 0:
        errors.append("Invalid hotkey: cannot be empty")

    if s.mode.lower() == "toggle":
        if not s.toggle_hotkey or len(s.toggle_hotkey.strip()) == 0:
            errors.append("Invalid toggle_hotkey: cannot be empty when mode is 'toggle'")

    # Valid indicator positions
    valid_positions = {
        "center", "top-left", "top-center", "top-right",
        "bottom-left", "bottom-center", "bottom-right",
        "left-center", "right-center"
    }
    if s.indicator_position.lower() not in valid_positions:
        errors.append(f"Invalid indicator_position '{s.indicator_position}'. Valid options: {', '.join(sorted(valid_positions))}")

    # Valid indicator sizes
    valid_sizes = {"small", "medium", "large"}
    if s.indicator_size.lower() not in valid_sizes:
        errors.append(f"Invalid indicator_size '{s.indicator_size}'. Valid options: {', '.join(sorted(valid_sizes))}")

    # If there are errors, print them and exit
    if errors:
        print("❌ Configuration validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  • {error}", file=sys.stderr)
        print(f"\nPlease fix your configuration in: {CONFIG_PATH}", file=sys.stderr)
        print("Or use environment variables (DICTATE_MODEL, DICTATE_DEVICE, etc.)", file=sys.stderr)
        sys.exit(1)

def load_config() -> Settings:
    s = Settings()
    config_loaded = False
    if os.path.exists(CONFIG_PATH):
        try:
            # tomllib (Python 3.11+) requires binary mode, toml library requires text mode
            file_mode = "rb" if _USE_TOMLLIB else "r"
            with open(CONFIG_PATH, file_mode) as f:
                data = tomllib.load(f)
            s.model = str(data.get("model", s.model))
            s.device = str(data.get("device", s.device))
            config_loaded = True
            s.hotkey = str(data.get("hotkey", s.hotkey))
            s.beeps = bool(data.get("beeps", s.beeps))
            s.smart_quotes = bool(data.get("smart_quotes", s.smart_quotes))
            s.mode = str(data.get("mode", s.mode))
            s.toggle_hotkey = str(data.get("toggle_hotkey", s.toggle_hotkey))
            s.mic = str(data.get("mic", s.mic))
            s.notify = bool(data.get("notify", s.notify))
            s.language = str(data.get("language", s.language))
            s.auto_space = bool(data.get("auto_space", s.auto_space))
            s.auto_period = bool(data.get("auto_period", s.auto_period))
            s.paste_injection = bool(data.get("paste_injection", s.paste_injection))
            s.injection_mode = str(data.get("injection_mode", s.injection_mode))
            s.auto_timeout_enabled = bool(data.get("auto_timeout_enabled", s.auto_timeout_enabled))
            s.auto_timeout_minutes = int(data.get("auto_timeout_minutes", s.auto_timeout_minutes))
            s.recording_indicator = bool(data.get("recording_indicator", s.recording_indicator))
            s.indicator_position = str(data.get("indicator_position", s.indicator_position))
            s.indicator_offset_x = int(data.get("indicator_offset_x", s.indicator_offset_x))
            s.indicator_offset_y = int(data.get("indicator_offset_y", s.indicator_offset_y))
            s.indicator_size = str(data.get("indicator_size", s.indicator_size))
            s.auto_check_updates = bool(data.get("auto_check_updates", s.auto_check_updates))
            s.last_update_check = str(data.get("last_update_check", s.last_update_check))
        except Exception as e:
            # Only print error once by using a module-level flag
            if not getattr(load_config, '_error_printed', False):
                print(f"⚠️  Error loading config from {CONFIG_PATH}: {e}", file=sys.stderr)
                load_config._error_printed = True

    # Environment overrides (optional)
    s.model = os.getenv("DICTATE_MODEL", s.model)
    s.device = os.getenv("DICTATE_DEVICE", s.device)
    s.hotkey = os.getenv("DICTATE_HOTKEY", s.hotkey)
    s.mode = os.getenv("DICTATE_MODE", s.mode)
    s.toggle_hotkey = os.getenv("DICTATE_TOGGLE_HOTKEY", s.toggle_hotkey)
    s.mic = os.getenv("DICTATE_MIC", s.mic)
    s.language = os.getenv("DICTATE_LANGUAGE", s.language)
    a = os.getenv("DICTATE_AUTO_SPACE");   s.auto_space = s.auto_space if a is None else a.lower() not in {"0","false","off","no"}
    p = os.getenv("DICTATE_AUTO_PERIOD");  s.auto_period = s.auto_period if p is None else p.lower() not in {"0","false","off","no"}
    pj = os.getenv("DICTATE_PASTE_INJECTION"); s.paste_injection = s.paste_injection if pj is None else pj.lower() not in {"0","false","off","no"}
    s.injection_mode = os.getenv("DICTATE_INJECTION_MODE", s.injection_mode)

    b = os.getenv("DICTATE_BEEPS");            s.beeps = s.beeps if b is None else b.lower() not in {"0","false","off","no"}
    q = os.getenv("DICTATE_SMART_QUOTES");     s.smart_quotes = s.smart_quotes if q is None else q.lower() not in {"0","false","off","no"}
    n = os.getenv("DICTATE_NOTIFY");           s.notify = s.notify if n is None else n.lower() not in {"0","false","off","no"}
    timeout_enabled = os.getenv("DICTATE_AUTO_TIMEOUT_ENABLED"); s.auto_timeout_enabled = s.auto_timeout_enabled if timeout_enabled is None else timeout_enabled.lower() not in {"0","false","off","no"}
    timeout_minutes = os.getenv("DICTATE_AUTO_TIMEOUT_MINUTES"); s.auto_timeout_minutes = s.auto_timeout_minutes if timeout_minutes is None else int(timeout_minutes)

    # Validate configuration before returning
    validate_config(s)

    return s

def save_config(s: Settings) -> None:
    """Save Settings to TOML file."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        f.write("# TalkType config\n")
        f.write(f'model = "{s.model}"\n')
        f.write(f'device = "{s.device}"\n')
        f.write(f'hotkey = "{s.hotkey}"\n')
        f.write(f'beeps = {str(s.beeps).lower()}\n')
        f.write(f'smart_quotes = {str(s.smart_quotes).lower()}\n')
        f.write(f'mode = "{s.mode}"\n')
        f.write(f'toggle_hotkey = "{s.toggle_hotkey}"\n')
        f.write(f'mic = "{s.mic}"\n')
        f.write(f'notify = {str(s.notify).lower()}\n')
        f.write(f'language = "{s.language}"\n')
        f.write(f'auto_space = {str(s.auto_space).lower()}\n')
        f.write(f'auto_period = {str(s.auto_period).lower()}\n')
        f.write(f'paste_injection = {str(s.paste_injection).lower()}\n')
        f.write(f'injection_mode = "{s.injection_mode}"\n')
        f.write(f'auto_timeout_enabled = {str(s.auto_timeout_enabled).lower()}\n')
        f.write(f'auto_timeout_minutes = {s.auto_timeout_minutes}\n')
        f.write(f'recording_indicator = {str(s.recording_indicator).lower()}\n')
        f.write(f'indicator_position = "{s.indicator_position}"\n')
        f.write(f'indicator_offset_x = {s.indicator_offset_x}\n')
        f.write(f'indicator_offset_y = {s.indicator_offset_y}\n')
        f.write(f'indicator_size = "{s.indicator_size}"\n')
        f.write(f'auto_check_updates = {str(s.auto_check_updates).lower()}\n')
        f.write(f'last_update_check = "{s.last_update_check}"\n')

def get_data_dir():
    """
    Get the data directory path based on dev mode.

    Returns:
        str: Path to ~/.local/share/TalkType (production) or ~/.local/share/TalkType-dev (dev mode)
    """
    return os.path.expanduser(f"~/.local/share/{DATA_DIR}")

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
            # tomllib (Python 3.11+) requires binary mode, toml library requires text mode
            file_mode = "rb" if _USE_TOMLLIB else "r"
            with open(CUSTOM_COMMANDS_PATH, file_mode) as f:
                data = tomllib.load(f)
            # Commands are stored under [commands] section
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
            # Escape quotes and handle multi-line strings
            escaped_replacement = replacement.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            f.write(f'"{phrase}" = "{escaped_replacement}"\n')

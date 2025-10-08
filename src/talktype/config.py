from __future__ import annotations
import os, tomllib
from dataclasses import dataclass
import sys

CONFIG_PATH = os.path.expanduser("~/.config/talktype/config.toml")

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
    notify: bool = True         # desktop notifications
    language: str = ""          # optional language code (e.g., "en"); empty = auto-detect
    auto_space: bool = True     # prepend a space before new utterance when not starting a new line/tab
    auto_period: bool = False   # append a period when an utterance ends without terminal punctuation
    paste_injection: bool = False  # when adding a leading space is unreliable, paste " ␣text" via clipboard
    injection_mode: str = "type"  # "type" (ydotool/wtype) or "paste" (wl-copy + Ctrl+V)
    auto_timeout_enabled: bool = False  # enable automatic timeout after inactivity
    auto_timeout_minutes: int = 5      # minutes of inactivity before auto-stop

def validate_config(s: Settings) -> None:
    """
    Validate configuration settings and exit with clear error message if invalid.

    Checks:
    - model: valid Whisper model name
    - device: "cpu" or "cuda"
    - mode: "hold" or "toggle"
    - auto_timeout_minutes: positive integer
    - injection_mode: "type" or "paste"
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
    if s.injection_mode.lower() not in {"type", "paste"}:
        errors.append(f"Invalid injection_mode '{s.injection_mode}'. Must be 'type' or 'paste'")

    # Auto-timeout minutes must be positive
    if s.auto_timeout_minutes <= 0:
        errors.append(f"Invalid auto_timeout_minutes '{s.auto_timeout_minutes}'. Must be positive")

    # Basic hotkey validation - just check it's not empty and looks reasonable
    if not s.hotkey or len(s.hotkey.strip()) == 0:
        errors.append("Invalid hotkey: cannot be empty")

    if s.mode.lower() == "toggle":
        if not s.toggle_hotkey or len(s.toggle_hotkey.strip()) == 0:
            errors.append("Invalid toggle_hotkey: cannot be empty when mode is 'toggle'")

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
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "rb") as f:
                data = tomllib.load(f)
            s.model = str(data.get("model", s.model))
            s.device = str(data.get("device", s.device))
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
        except Exception:
            pass

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

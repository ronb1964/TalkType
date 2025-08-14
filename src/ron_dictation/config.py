from __future__ import annotations
import os, tomllib
from dataclasses import dataclass

CONFIG_PATH = os.path.expanduser("~/.config/ron-dictation/config.toml")

@dataclass
class Settings:
    model: str = "small"        # tiny/base/small/medium/large-v3 …
    device: str = "cpu"         # "cpu" or "cuda"
    hotkey: str = "F8"          # hold-to-talk hotkey
    beeps: bool = True          # beeps on/off
    smart_quotes: bool = True   # “smart quotes”
    mode: str = "hold"          # "hold" or "toggle"
    toggle_hotkey: str = "F9"   # used only when mode="toggle"
    mic: str = ""               # substring to match input device (empty = default)
    notify: bool = True         # desktop notifications
    language: str = ""          # optional language code (e.g., "en"); empty = auto-detect
    auto_space: bool = True     # prepend a space before new utterance when not starting a new line/tab

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

    b = os.getenv("DICTATE_BEEPS");            s.beeps = s.beeps if b is None else b.lower() not in {"0","false","off","no"}
    q = os.getenv("DICTATE_SMART_QUOTES");     s.smart_quotes = s.smart_quotes if q is None else q.lower() not in {"0","false","off","no"}
    n = os.getenv("DICTATE_NOTIFY");           s.notify = s.notify if n is None else n.lower() not in {"0","false","off","no"}

    return s

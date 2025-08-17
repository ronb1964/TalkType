from __future__ import annotations
import os
from dataclasses import dataclass

try:
    import tomllib
    def _load_toml(path: str) -> dict:
        with open(path, "rb") as f:
            return tomllib.load(f)
except ModuleNotFoundError:
    import toml
    def _load_toml(path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return toml.load(f)

CONFIG_PATH = os.path.expanduser("~/.config/talktype/config.toml")

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
    auto_period: bool = False   # append a period when an utterance ends without terminal punctuation
    paste_injection: bool = False  # when adding a leading space is unreliable, paste " ␣text" via clipboard
    injection_mode: str = "type"  # "type" (ydotool/wtype) or "paste" (wl-copy + Ctrl+V)

def load_config() -> Settings:
    s = Settings()
    if os.path.exists(CONFIG_PATH):
        try:
            data = _load_toml(CONFIG_PATH)
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

    return s

"""What TalkType should run on this computer.

How fast and accurate dictation is depends on the model, the device and the
language, and they only work in some combinations: Parakeet knows 25
languages and can't use CUDA; large-v3 needs a graphics card; a small
built-in graphics chip can be slower than the processor. This module turns
the facts about the computer and the user's language into one Setup. First
run, the tray presets, the GNOME menu (over D-Bus) and the update notice all
ask it, so they can't disagree. Pure logic apart from detect_hardware().
"""
import functools
import os
from dataclasses import dataclass

from .parakeet_engine import PARAKEET_LANGUAGES

PARAKEET = "parakeet-v3"

LANGUAGES = [
    ("en", "English"), ("es", "Spanish"), ("fr", "French"), ("de", "German"),
    ("it", "Italian"), ("pt", "Portuguese"), ("ru", "Russian"), ("ja", "Japanese"),
    ("ko", "Korean"), ("zh", "Chinese"), ("ar", "Arabic"), ("hi", "Hindi"),
    ("nl", "Dutch"), ("sv", "Swedish"), ("no", "Norwegian"), ("da", "Danish"),
    ("fi", "Finnish"), ("pl", "Polish"), ("tr", "Turkish"), ("he", "Hebrew"),
    ("th", "Thai"), ("vi", "Vietnamese"), ("uk", "Ukrainian"), ("cs", "Czech"),
    ("hu", "Hungarian"), ("ro", "Romanian"), ("bg", "Bulgarian"), ("hr", "Croatian"),
    ("sk", "Slovak"), ("sl", "Slovenian"), ("et", "Estonian"), ("lv", "Latvian"),
    ("lt", "Lithuanian"), ("el", "Greek"), ("mt", "Maltese"),
]
_NAMES = dict(LANGUAGES)

_TITLES = {PARAKEET: "Parakeet", "small": "Whisper Small", "large-v3": "Whisper Large-v3",
           "base": "Whisper Base", "tiny": "Whisper Tiny"}

_BENEFIT = {
    (PARAKEET, "vulkan"): "Very accurate and nearly instant.",
    (PARAKEET, "cpu"): "Very accurate, and fast even without a graphics card.",
    ("small", "vulkan"): "Knows 99 languages. Quick on most computers.",
    ("small", "cpu"): "Knows 99 languages. Quick on most computers.",
    ("large-v3", "vulkan"): "Whisper's most accurate, and it knows 99 languages.",
}

_DOWNLOAD = {
    (PARAKEET, "vulkan"): "About 700 MB",
    (PARAKEET, "cpu"): "About 670 MB",
    ("small", "vulkan"): "About 280 MB",
    ("small", "cpu"): "About 250 MB",
    ("large-v3", "vulkan"): "About 1 GB",
}


def language_name(code):
    return _NAMES.get(code, code)


def system_language(env=None):
    """ISO 639-1 code of the desktop's language, from the locale variables."""
    env = os.environ if env is None else env
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = (env.get(var) or "").strip()
        if not value or value == "POSIX" or value.split(".")[0] == "C":
            continue
        code = value.split(".")[0].split("@")[0].split("_")[0].lower()
        if code.isalpha() and 2 <= len(code) <= 3:
            return code
    return "en"


def effective_language(cfg):
    """The language to recommend for: the first-run choice, then a language
    picked by hand in Preferences (so an existing Japanese setup isn't
    switched to Parakeet), then the desktop's language."""
    chosen = getattr(cfg, "dictation_language", "") or ""
    if chosen:
        return chosen
    if getattr(cfg, "language_mode", "auto") == "manual" and getattr(cfg, "language", ""):
        return cfg.language
    return system_language()


@dataclass(frozen=True)
class Hardware:
    gpu_name: str | None      # None: no graphics chip worth using
    has_nvidia: bool = False

    @property
    def gpu(self):
        return self.gpu_name is not None


@functools.lru_cache(maxsize=1)
def _nvidia_name():
    """The NVIDIA card's name from nvidia-smi, once per process."""
    try:
        from .cuda_helper import detect_nvidia_gpu
        found = detect_nvidia_gpu()
    except Exception:
        return None
    if isinstance(found, str) and found.strip():
        return found.strip().splitlines()[0]
    return None


@functools.lru_cache(maxsize=1)
def _vulkan_facts():
    """(Vulkan usable, graphics vendor ids), once per process."""
    from . import whisper_vulkan as wv
    return wv.is_offered(), frozenset(wv.graphics_vendors())


def detect_hardware(cfg=None):
    """The graphics chip TalkType should use, if any. Never raises.

    No chip on the Flatpak (no Vulkan engine in the sandbox), and none once
    the speed check found the processor faster (cfg.vulkan_slower), so a
    small built-in chip isn't recommended over and over."""
    if os.environ.get("FLATPAK_ID"):
        return Hardware(None, False)
    try:
        usable, vendors = _vulkan_facts()
    except Exception:
        return Hardware(None, False)
    from . import whisper_vulkan as wv
    nvidia = _nvidia_name()
    has_nvidia = bool(nvidia) or wv.NVIDIA_VENDOR in vendors
    if not usable or (cfg is not None and getattr(cfg, "vulkan_slower", False)):
        return Hardware(None, has_nvidia)
    if has_nvidia:
        name = nvidia or "NVIDIA graphics card"
    elif wv.AMD_VENDOR in vendors:
        name = "AMD graphics"
    elif wv.INTEL_VENDOR in vendors:
        name = "Intel graphics"
    else:
        name = "graphics card"
    return Hardware(name, has_nvidia)


@dataclass(frozen=True)
class Setup:
    model: str
    device: str
    title: str
    explanation: str
    download_text: str


def recommend(language, hw, model=None, use_gpu=None):
    """The setup for this computer. *model* and *use_gpu* are the user's own
    choices from Other options; one that can't work is replaced, and the
    explanation says why."""
    language = language or "en"
    name = language_name(language)
    parakeet_ok = language in PARAKEET_LANGUAGES
    gpu = hw.gpu if use_gpu is None else bool(use_gpu and hw.gpu)
    note = ""
    if model in (None, PARAKEET) and not parakeet_ok:
        note = (f"Parakeet doesn't understand {name}, so this uses Whisper, "
                "which knows 99 languages. ")
        model = "large-v3" if gpu else "small"
    elif model is None:
        model = PARAKEET
    elif model == "large-v3" and not gpu:
        note = ("Large-v3 needs a graphics card, so this uses Whisper Small "
                "on the processor. ")
        model = "small"
    device = "vulkan" if gpu else "cpu"
    where = f"your {hw.gpu_name}" if gpu else "this computer's processor"
    return Setup(
        model=model,
        device=device,
        title=f"{_TITLES[model]} on {where}",
        explanation=note + _BENEFIT[(model, device)],
        download_text=_DOWNLOAD[(model, device)] + ", downloaded once.",
    )


@dataclass(frozen=True)
class OptionState:
    model: str
    label: str
    size: str
    description: str
    available: bool
    reason: str


def option_states(language, hw):
    """The models offered under Other options, each with why it can't be
    picked when it can't. Tiny, Base and Medium live in Preferences."""
    name = language_name(language or "en")
    parakeet_ok = (language or "en") in PARAKEET_LANGUAGES
    return [
        OptionState(PARAKEET, "Parakeet", "670 MB",
                    "The most accurate for English and 24 European languages. "
                    "Fast even without a graphics card.",
                    parakeet_ok, "" if parakeet_ok else f"Doesn't understand {name}."),
        OptionState("small", "Whisper Small", "250 MB",
                    "Knows 99 languages. A good choice on an older or slower computer.",
                    True, ""),
        OptionState("large-v3", "Whisper Large-v3", "about 1 GB",
                    "Whisper's most accurate, for languages Parakeet doesn't know. "
                    "Needs a graphics card.",
                    hw.gpu, "" if hw.gpu else "Needs a graphics card."),
    ]


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    description: str
    model: str
    device: str
    extras: tuple = ()      # ((config key, value), ...)


def presets(language, hw):
    """The tray's Performance menu, in order."""
    rec = recommend(language, hw)
    return [
        Preset("recommended", "Recommended for this computer", rec.title, rec.model, rec.device),
        Preset("lightest", "Lightest",
               "Whisper Base on the processor: the smallest download and the least work",
               "base", "cpu"),
        Preset("battery", "Battery saver",
               "Whisper Tiny on the processor, stops after 2 idle minutes",
               "tiny", "cpu",
               (("auto_timeout_enabled", True), ("auto_timeout_minutes", 2))),
    ]


def match_preset(cfg, preset_list):
    """Id of the preset the settings match, or "custom". Presets with extra
    settings are checked first, since they share a model and device with
    nothing else but must also match their extras."""
    def same(p):
        return (getattr(cfg, "model", None) == p.model
                and getattr(cfg, "device", None) == p.device
                and all(getattr(cfg, k, None) == v for k, v in p.extras))
    for p in sorted(preset_list, key=lambda p: not p.extras):
        if same(p):
            return p.id
    return "custom"


def differs_from_recommendation(cfg, hw):
    """The recommended Setup when the settings aren't it, else None."""
    rec = recommend(effective_language(cfg), hw)
    if (getattr(cfg, "model", None), getattr(cfg, "device", None)) == (rec.model, rec.device):
        return None
    return rec

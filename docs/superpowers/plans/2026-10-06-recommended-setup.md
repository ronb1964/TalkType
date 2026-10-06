# Recommended Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** New users land on the best setup for their computer with one click: a recommendation card at first run, three outcome presets, and a one-time notice for existing users.

**Architecture:** One pure-logic module, `recommend.py`, turns computer facts (graphics card) and the dictation language into a `Setup` (model, device, wording). First run, the tray presets, the GNOME extension (through D-Bus) and the update notice all ask it, so they can't disagree. GTK code only renders what `recommend.py` returns.

**Tech Stack:** Python 3 + GTK3 (PyGObject), dbus-python, GNOME Shell extension (GJS), pytest.

**Spec:** `docs/superpowers/specs/2026-10-06-recommended-setup-design.md`

## Global Constraints

- Run tests with: `PYTHONPATH=src:/usr/lib64/python3.14/site-packages:/usr/lib/python3.14/site-packages .venv/bin/python -m pytest tests/ -q -p no:cacheprovider` (bare `pytest` fails to import PyGObject).
- Model ids: `"parakeet-v3"` (Parakeet), `"tiny"`, `"base"`, `"small"`, `"medium"`, `"large-v3"`. Device ids: `"cpu"`, `"cuda"`, `"vulkan"`.
- Preset ids are exactly `"recommended"`, `"lightest"`, `"battery"`. Labels are exactly "Recommended for this computer", "Lightest", "Battery saver".
- Lightest = Whisper Base on the processor. Battery saver = Whisper Tiny on the processor with `auto_timeout_enabled=True`, `auto_timeout_minutes=2`. (Lightest is Base, not Small, because Small is what Recommended picks without a graphics card for non-European languages, and the two must never coincide.)
- First run never offers or downloads CUDA. CUDA stays in Preferences.
- Existing users' model and device are never changed except by their own choice.
- The GNOME extension is `gnome-extension/talktype@ronb1964.github.io/`; its version goes from 14 to 15.
- UI copy follows the approved mockup wording; no em dashes in new user-facing strings.
- Don't set `GDK_BACKEND` anywhere. Launch any UI with `env -u GDK_BACKEND`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A weak built-in graphics chip** (speed check says the processor is faster): Recommended must then mean the processor. Otherwise the update notice nags forever and the Recommended dot never shows. Covered by `vulkan_slower` in Task 1 (recommend) and Task 6 (flag set by the speed check).
2. **A Japanese user who set Whisper with manual language "ja" before this feature** (no `dictation_language` yet): the recommendation must not switch them to Parakeet. Covered by `effective_language()` in Task 1.
3. **An old GNOME extension (v14) sending old preset ids** ("balanced", "accurate"...) to the new tray: ignored with a log line, the radio reverts, nothing crashes. Covered in Task 3.
4. **Cancelling the Vulkan download confirm when choosing Recommended**: nothing changes. It must not quietly apply the processor instead. Covered in Task 3.
5. **The tray polls the active preset every second**: hardware detection runs nvidia-smi, which must not run each second. Covered by caching in Task 1 (`_nvidia_name` and `_vulkan_facts` cached).

---

### Task 1: `recommend.py`, the recommendation logic

**Files:**
- Create: `src/talktype/recommend.py`
- Modify: `src/talktype/config.py` (Settings fields + LIVE_APPLIED_KEYS)
- Test: `tests/test_recommend.py`

**Interfaces:**
- Consumes: `parakeet_engine.PARAKEET_LANGUAGES` (frozenset of 25 ISO codes); `whisper_vulkan.is_offered()`, `whisper_vulkan.graphics_vendors()`, `whisper_vulkan.NVIDIA_VENDOR/AMD_VENDOR/INTEL_VENDOR`; `cuda_helper.detect_nvidia_gpu()` (returns the GPU name string, or a falsy value).
- Produces:
  - `Hardware(gpu_name: str | None, has_nvidia: bool = False)`, frozen, with property `gpu -> bool`
  - `detect_hardware(cfg=None) -> Hardware`
  - `system_language(env=None) -> str`
  - `effective_language(cfg) -> str`
  - `language_name(code) -> str`
  - `LANGUAGES: list[tuple[str, str]]`
  - `Setup(model, device, title, explanation, download_text)`, frozen
  - `recommend(language, hw, model=None, use_gpu=None) -> Setup`
  - `OptionState(model, label, size, description, available, reason)`, frozen
  - `option_states(language, hw) -> list[OptionState]`
  - `Preset(id, label, description, model, device, extras)`, frozen, with `extras` a tuple of `(key, value)`
  - `presets(language, hw) -> list[Preset]`
  - `match_preset(cfg, preset_list) -> str` (an id or `"custom"`)
  - `differs_from_recommendation(cfg, hw) -> Setup | None`
  - `config.Settings.dictation_language: str = ""`, `.recommend_notice_shown: bool = False`, `.vulkan_slower: bool = False`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_recommend.py
"""recommend.py: the best setup for this computer, in one place.

First run, the tray presets, the GNOME menu and the update notice all ask
recommend(), so they can't disagree. Pure logic: hardware and language in,
setup out.
"""
import types

import pytest

from talktype import recommend as r

NVIDIA = r.Hardware("NVIDIA GeForce RTX 4070 SUPER", has_nvidia=True)
AMD = r.Hardware("AMD graphics")
NONE = r.Hardware(None)


@pytest.mark.parametrize("lang,hw,model,device", [
    ("en", NVIDIA, "parakeet-v3", "vulkan"),
    ("uk", AMD, "parakeet-v3", "vulkan"),
    ("en", NONE, "parakeet-v3", "cpu"),
    ("ja", NVIDIA, "large-v3", "vulkan"),
    ("ja", NONE, "small", "cpu"),
])
def test_recommendation_per_computer(lang, hw, model, device):
    s = r.recommend(lang, hw)
    assert (s.model, s.device) == (model, device)


def test_titles_name_the_graphics_card_or_processor():
    assert r.recommend("en", NVIDIA).title == "Parakeet on your NVIDIA GeForce RTX 4070 SUPER"
    assert r.recommend("en", NONE).title == "Parakeet on this computer's processor"
    assert r.recommend("ja", NVIDIA).title == "Whisper Large-v3 on your NVIDIA GeForce RTX 4070 SUPER"


def test_a_language_parakeet_lacks_says_why():
    s = r.recommend("ja", NVIDIA)
    assert "Parakeet doesn't understand Japanese" in s.explanation


def test_overrides_are_honoured_or_explained():
    assert r.recommend("en", NVIDIA, model="small").model == "small"
    assert r.recommend("en", NVIDIA, use_gpu=False).device == "cpu"
    s = r.recommend("ja", NVIDIA, model="parakeet-v3")        # can't work
    assert s.model == "large-v3" and "doesn't understand" in s.explanation
    s = r.recommend("en", NONE, model="large-v3")              # needs a GPU
    assert s.model == "small" and "needs a graphics card" in s.explanation.lower()


def test_download_text_matches_the_setup():
    assert r.recommend("en", NVIDIA).download_text == "About 700 MB, downloaded once."
    assert r.recommend("en", NONE).download_text == "About 670 MB, downloaded once."
    assert r.recommend("ja", NVIDIA).download_text == "About 1 GB, downloaded once."


def test_option_states_grey_out_what_cant_work():
    states = {o.model: o for o in r.option_states("ja", NONE)}
    assert not states["parakeet-v3"].available
    assert states["parakeet-v3"].reason == "Doesn't understand Japanese."
    assert not states["large-v3"].available
    assert states["large-v3"].reason == "Needs a graphics card."
    assert states["small"].available
    assert all(o.available for o in r.option_states("en", NVIDIA))


@pytest.mark.parametrize("env,code", [
    ({"LANG": "en_US.UTF-8"}, "en"),
    ({"LANG": "uk_UA.UTF-8"}, "uk"),
    ({"LC_ALL": "ja_JP.UTF-8", "LANG": "en_US.UTF-8"}, "ja"),
    ({"LANG": "C.UTF-8"}, "en"),
    ({"LANG": "sr_RS@latin"}, "sr"),
    ({}, "en"),
])
def test_system_language(env, code):
    assert r.system_language(env) == code


def test_effective_language_order(monkeypatch):
    monkeypatch.setattr(r, "system_language", lambda env=None: "en")
    cfg = types.SimpleNamespace(dictation_language="", language_mode="manual", language="ja")
    assert r.effective_language(cfg) == "ja"           # an old manual choice counts
    cfg.dictation_language = "de"
    assert r.effective_language(cfg) == "de"           # the first-run choice wins
    cfg2 = types.SimpleNamespace(dictation_language="", language_mode="auto", language="")
    assert r.effective_language(cfg2) == "en"          # the system locale


def test_presets_have_stable_ids_and_never_coincide():
    for lang in ("en", "ja"):
        for hw in (NVIDIA, AMD, NONE):
            ps = r.presets(lang, hw)
            assert [p.id for p in ps] == ["recommended", "lightest", "battery"]
            pairs = [(p.model, p.device, p.extras) for p in ps]
            assert len(set(pairs)) == 3, (lang, hw, pairs)
    battery = r.presets("en", NONE)[2]
    assert (battery.model, battery.device) == ("tiny", "cpu")
    assert dict(battery.extras) == {"auto_timeout_enabled": True, "auto_timeout_minutes": 2}
    assert r.presets("en", NONE)[1].model == "base"


def _cfg(model, device, timeout_on=True, minutes=5):
    return types.SimpleNamespace(model=model, device=device, auto_timeout_enabled=timeout_on,
                                 auto_timeout_minutes=minutes, dictation_language="",
                                 language_mode="auto", language="")


def test_match_preset():
    ps = r.presets("en", NVIDIA)
    assert r.match_preset(_cfg("parakeet-v3", "vulkan"), ps) == "recommended"
    assert r.match_preset(_cfg("base", "cpu"), ps) == "lightest"
    assert r.match_preset(_cfg("tiny", "cpu", True, 2), ps) == "battery"
    assert r.match_preset(_cfg("tiny", "cpu", True, 5), ps) == "custom"
    assert r.match_preset(_cfg("parakeet-v3", "cpu"), ps) == "custom"   # GPU idle: not Recommended


def test_differs_from_recommendation(monkeypatch):
    monkeypatch.setattr(r, "system_language", lambda env=None: "en")
    assert r.differs_from_recommendation(_cfg("parakeet-v3", "vulkan"), NVIDIA) is None
    s = r.differs_from_recommendation(_cfg("small", "cpu"), NVIDIA)
    assert s is not None and s.model == "parakeet-v3"


def test_a_slower_graphics_chip_means_the_processor(monkeypatch):
    """Review focus 1: once the speed check said the processor wins, recommend it."""
    monkeypatch.setattr(r, "_vulkan_facts", lambda: (True, frozenset({"0x8086"})))
    monkeypatch.setattr(r, "_nvidia_name", lambda: None)
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    fast = r.detect_hardware(types.SimpleNamespace(vulkan_slower=False))
    slow = r.detect_hardware(types.SimpleNamespace(vulkan_slower=True))
    assert fast.gpu and fast.gpu_name == "Intel graphics"
    assert not slow.gpu


def test_flatpak_has_no_usable_graphics(monkeypatch):
    monkeypatch.setenv("FLATPAK_ID", "io.github.ronb1964.TalkType")
    assert not r.detect_hardware().gpu


def test_detect_hardware_never_raises(monkeypatch):
    def boom():
        raise OSError("no sysfs")
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setattr(r, "_vulkan_facts", boom)
    monkeypatch.setattr(r, "_nvidia_name", lambda: None)
    assert r.detect_hardware() == r.Hardware(None, False)


def test_hardware_facts_are_cached():
    """Review focus 5: the tray asks every second; nvidia-smi must run once."""
    assert hasattr(r._nvidia_name, "cache_info") and hasattr(r._vulkan_facts, "cache_info")


def test_new_settings_exist_and_are_live():
    from talktype.config import LIVE_APPLIED_KEYS, Settings
    s = Settings()
    assert (s.dictation_language, s.recommend_notice_shown, s.vulkan_slower) == ("", False, False)
    assert {"dictation_language", "recommend_notice_shown", "vulkan_slower"} <= LIVE_APPLIED_KEYS
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:/usr/lib64/python3.14/site-packages:/usr/lib/python3.14/site-packages .venv/bin/python -m pytest tests/test_recommend.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'recommend'`.

- [ ] **Step 3: Add the config fields**

In `src/talktype/config.py`, after `typing_wpm: int = 40 ...` add:

```python
    dictation_language: str = ""         # language picked at first run (recommend.py); "" = system locale
    recommend_notice_shown: bool = False  # the one-time "better setup" notice was shown (or not needed)
    vulkan_slower: bool = False          # the speed check found the processor faster than the graphics chip
```

and in `LIVE_APPLIED_KEYS`, after `"restore_clipboard",` add:

```python
    # Read by the tray and first run (recommend.py), never by the service.
    "dictation_language",
    "recommend_notice_shown",
    "vulkan_slower",
```

- [ ] **Step 4: Write `recommend.py`**

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH=src:/usr/lib64/python3.14/site-packages:/usr/lib/python3.14/site-packages .venv/bin/python -m pytest tests/test_recommend.py -q -p no:cacheprovider`
Expected: all PASS. Then run the full suite: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/talktype/recommend.py src/talktype/config.py tests/test_recommend.py
git commit -m "Add recommend.py: the best setup for this computer, in one place

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Remember when the processor beat the graphics chip

**Files:**
- Modify: `src/talktype/vulkan_setup_dialogs.py` (`run_speed_check`)
- Test: `tests/test_whisper_vulkan.py` (append)

**Interfaces:**
- Consumes: `config.load_config/save_config`, `Settings.vulkan_slower` (Task 1).
- Produces: after `run_speed_check`, `vulkan_slower` is True if the processor won, False if the graphics chip won, unchanged on an error.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_whisper_vulkan.py`)

```python
@pytest.mark.parametrize("times,slower", [((1.0, 5.0), False), ((5.0, 1.0), True)])
def test_speed_check_remembers_which_won(monkeypatch, times, slower):
    """Review focus 1: recommend.py must not keep proposing a slower chip."""
    from talktype import vulkan_setup_dialogs as vsd
    saved = {}
    cfg = types.SimpleNamespace(vulkan_slower=not slower)
    monkeypatch.setattr(vsd.wv, "find_device", lambda: 0)
    monkeypatch.setattr(vsd.wv, "speed_check", lambda model, dev: times)
    monkeypatch.setattr(vsd, "message", lambda *a, **k: None)
    monkeypatch.setattr("talktype.config.load_config", lambda: cfg)
    monkeypatch.setattr("talktype.config.save_config", lambda c: saved.update(slower=c.vulkan_slower))
    monkeypatch.setattr(vsd, "_wait_dialog", lambda parent, work: work())
    vsd.run_speed_check(None, "small")
    assert saved == {"slower": slower}
```

(Add `import types` at the top of the test file if it isn't there.)

- [ ] **Step 2: Run it to verify it fails**

Run: `... -m pytest tests/test_whisper_vulkan.py -q -p no:cacheprovider -k remembers`
Expected: FAIL (`_wait_dialog` doesn't exist; nothing is saved).

- [ ] **Step 3: Implement**

In `vulkan_setup_dialogs.py`, move the spinner/thread/poll block of `run_speed_check` into a helper and record the result:

```python
def _wait_dialog(parent, work):
    """Run *work* on a thread behind a modal "Checking Speed" spinner."""
    waiting = Gtk.Dialog(title="Checking Speed", transient_for=parent, modal=True)
    waiting.set_deletable(False)
    waiting.set_keep_above(True)
    box = waiting.get_content_area()
    box.set_spacing(12)
    box.set_border_width(18)
    row = Gtk.Box(spacing=12)
    spinner = Gtk.Spinner()
    spinner.start()
    row.pack_start(spinner, False, False, 0)
    row.pack_start(Gtk.Label(label="Checking how fast your graphics chip is compared to your\n"
                                   "processor. This can take up to a minute.", xalign=0),
                   False, False, 0)
    box.add(row)
    waiting.show_all()
    thread = threading.Thread(target=work, daemon=True)
    thread.start()

    def poll():
        if thread.is_alive():
            return True
        waiting.response(Gtk.ResponseType.OK)
        return False

    GLib.timeout_add(200, poll)
    waiting.run()
    waiting.destroy()


def _remember_speed_result(processor_won):
    """recommend.py stops proposing the graphics chip once it lost (vulkan_slower)."""
    try:
        from .config import load_config, save_config
        cfg = load_config()
        if cfg.vulkan_slower != processor_won:
            cfg.vulkan_slower = processor_won
            save_config(cfg)
    except Exception:
        pass
```

and `run_speed_check` becomes:

```python
def run_speed_check(parent, model):
    """Time the graphics chip against the processor on a short sample, tell
    the user the result, and return True if the graphics chip should be used."""
    result = {}

    def work():
        try:
            device = wv.find_device()
            if device is None:
                result["error"] = "TalkType couldn't find a graphics chip it can use."
            else:
                result["times"] = wv.speed_check(model, device)
        except Exception as e:
            result["error"] = f"The speed check didn't work: {e}"

    _wait_dialog(parent, work)

    if "error" in result:
        message(parent, Gtk.MessageType.WARNING, "Keeping the processor", result["error"])
        return False
    gpu, cpu = result["times"]
    if wv.graphics_is_worth_it(gpu, cpu):
        _remember_speed_result(False)
        message(parent, Gtk.MessageType.INFO, "Your graphics chip is faster",
                f"It transcribed the test in {gpu:.1f} seconds, your processor in {cpu:.1f}, "
                f"about {cpu / gpu:.0f} times faster. TalkType will use your graphics chip.")
        return True
    _remember_speed_result(True)
    message(parent, Gtk.MessageType.INFO, "Your processor is faster here",
            f"Your processor transcribed the test in {cpu:.1f} seconds and your graphics chip "
            f"in {gpu:.1f}. The graphics built into some processors is too small to help, so "
            "TalkType will keep using the processor.")
    return False
```

- [ ] **Step 4: Run the tests**: the new test passes, and the full suite passes.

- [ ] **Step 5: Commit**

```bash
git add src/talktype/vulkan_setup_dialogs.py tests/test_whisper_vulkan.py
git commit -m "Remember when the speed check finds the processor faster

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Tray presets from recommend.py, plus D-Bus GetPresets

**Files:**
- Modify: `src/talktype/tray.py`:
  - remove `PERFORMANCE_PRESETS`, `_PRESET_EXTRA_KEYS` and `_download_cuda_for_most_accurate`;
  - rewrite `_get_current_preset`, `set_performance_preset` and `_build_performance_submenu`;
  - `update_menu_display` refreshes labels;
  - `TrayAppInstance` gains `get_presets` and `current_preset`.
- Modify: `src/talktype/dbus_service.py`: `GetPresets`, and `preset` in `GetStatus`.
- Modify: `src/talktype/help_dialog.py`: the presets paragraph.
- Delete (replaced by the new tests): `tests/test_preset_selection.py`, `tests/test_presets_vulkan.py`, `tests/test_preset_dot_parity.py`.
- Test: `tests/test_tray_presets.py` (new), `tests/test_help_feedback_link.py` (its preset test now reads `recommend.presets`).

**Interfaces:**
- Consumes: `recommend.presets`, `recommend.match_preset`, `recommend.detect_hardware`, `recommend.effective_language`; `vulkan_setup_dialogs.ensure_files(parent, model, confirm) -> bool`, `vulkan_setup_dialogs.run_speed_check(parent, model) -> bool`; `model_helper.is_model_cached_fast`, `download_model_with_progress`; `preset_notice(label, model, device, gpu_offered)` (already in tray.py).
- Produces:
  - `DictationTray._current_presets() -> list[recommend.Preset]`
  - `DictationTray._get_current_preset() -> str`
  - `DictationTray.set_performance_preset(preset_id)`
  - D-Bus `GetPresets() -> a(sss)`
  - `GetStatus()["preset"] -> s`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tray_presets.py
"""The tray's Performance menu: three outcome presets from recommend.py.

Seven model-named presets used to promise "GPU" and silently use the
processor. Now Recommended for this computer / Lightest / Battery saver come
from recommend.presets(), so the menu, first run and the GNOME menu agree.
"""
import types

import pytest

from talktype import recommend as r
from talktype import tray as tray_mod

NVIDIA = r.Hardware("NVIDIA GeForce RTX 4070 SUPER", has_nvidia=True)


class FakeTray:
    _current_presets = tray_mod.DictationTray._current_presets
    _get_current_preset = tray_mod.DictationTray._get_current_preset
    set_performance_preset = tray_mod.DictationTray.set_performance_preset

    def __init__(self):
        self.reverted = 0
        self.restarted = 0
        self.preset_radios = {}

    def _revert_preset_radio(self):
        self.reverted += 1

    def update_menu_display(self, is_running=None):
        pass

    def _emit_model_changed(self, model):
        pass

    def restart_service(self, _):
        self.restarted += 1


@pytest.fixture
def env(monkeypatch):
    cfg = types.SimpleNamespace(model="small", device="cpu", auto_timeout_enabled=True,
                                auto_timeout_minutes=5, dictation_language="en",
                                language_mode="auto", language="", vulkan_slower=False)
    saved = []
    monkeypatch.setattr("talktype.config.load_config", lambda: cfg)
    monkeypatch.setattr("talktype.config.save_config", lambda c: saved.append((c.model, c.device)))
    monkeypatch.setattr(r, "detect_hardware", lambda cfg=None: NVIDIA)
    monkeypatch.setattr("talktype.model_helper.is_model_cached_fast", lambda m: True)
    monkeypatch.setattr("talktype.app._notify", lambda t, b: None)
    monkeypatch.setattr("talktype.whisper_vulkan.is_offered", lambda: True)
    return cfg, saved


def test_three_presets_in_order(env):
    assert [p.id for p in FakeTray()._current_presets()] == ["recommended", "lightest", "battery"]


def test_recommended_runs_the_vulkan_setup_then_saves(env, monkeypatch):
    cfg, saved = env
    calls = []
    monkeypatch.setattr("talktype.vulkan_setup_dialogs.ensure_files",
                        lambda p, m, confirm: calls.append(("files", m)) or True)
    monkeypatch.setattr("talktype.vulkan_setup_dialogs.run_speed_check",
                        lambda p, m: calls.append(("speed", m)) or True)
    t = FakeTray()
    t.set_performance_preset("recommended")
    assert calls == [("files", "parakeet-v3"), ("speed", "parakeet-v3")]
    assert saved == [("parakeet-v3", "vulkan")] and t.restarted == 1


def test_recommended_falls_back_to_the_processor_when_it_is_faster(env, monkeypatch):
    cfg, saved = env
    monkeypatch.setattr("talktype.vulkan_setup_dialogs.ensure_files", lambda p, m, confirm: True)
    monkeypatch.setattr("talktype.vulkan_setup_dialogs.run_speed_check", lambda p, m: False)
    FakeTray().set_performance_preset("recommended")
    assert saved == [("parakeet-v3", "cpu")]


def test_cancelling_the_download_changes_nothing(env, monkeypatch):
    """Review focus 4."""
    cfg, saved = env
    monkeypatch.setattr("talktype.vulkan_setup_dialogs.ensure_files", lambda p, m, confirm: False)
    t = FakeTray()
    t.set_performance_preset("recommended")
    assert saved == [] and t.reverted == 1 and t.restarted == 0


def test_battery_saver_sets_its_timeout(env):
    cfg, saved = env
    FakeTray().set_performance_preset("battery")
    assert saved == [("tiny", "cpu")]
    assert (cfg.auto_timeout_enabled, cfg.auto_timeout_minutes) == (True, 2)


@pytest.mark.parametrize("old_id", ["balanced", "accurate", "parakeet", "fastest", "custom"])
def test_old_or_unknown_ids_are_ignored(env, old_id):
    """Review focus 3: an older GNOME extension sends the old ids."""
    cfg, saved = env
    t = FakeTray()
    t.set_performance_preset(old_id)
    assert saved == [] and t.restarted == 0


def test_current_preset_uses_match_preset(env):
    cfg, _ = env
    cfg.model, cfg.device = "parakeet-v3", "vulkan"
    assert FakeTray()._get_current_preset() == "recommended"
    cfg.model, cfg.device = "medium", "cuda"
    assert FakeTray()._get_current_preset() == "custom"


def test_dbus_exposes_presets_and_the_active_one():
    from talktype.dbus_service import TalkTypeDBusService
    svc = TalkTypeDBusService.__new__(TalkTypeDBusService)
    svc.running_engine = None
    svc.claimed_hotkeys = []
    svc.app = types.SimpleNamespace(
        get_presets=lambda: [("recommended", "Recommended for this computer", "x")],
        current_preset=lambda: "recommended",
        config=types.SimpleNamespace(model="parakeet-v3", device="vulkan",
                                     auto_timeout_enabled=True, auto_timeout_minutes=5),
        is_recording=False, service_running=True)
    svc.IsRecording = lambda: False
    svc.IsServiceRunning = lambda: True
    svc.GetInjectionMode = lambda: "auto"
    assert list(svc.GetPresets()) == [("recommended", "Recommended for this computer", "x")]
    assert svc.GetStatus()["preset"] == "recommended"


def test_old_preset_table_is_gone():
    src = (tray_mod.__file__)
    text = open(src).read()
    assert "PERFORMANCE_PRESETS" not in text and "_download_cuda_for_most_accurate" not in text
```

Change `test_help_lists_every_tray_preset` in `tests/test_help_feedback_link.py` to:

```python
def test_help_lists_every_tray_preset(dialog):
    """Help listed 5 of the 7 old presets; it must name each of today's."""
    from talktype import recommend
    text = "\n".join(l.get_text() for l in _help_labels(dialog))
    for preset in recommend.presets("en", recommend.Hardware(None)):
        assert f"{preset.label}:" in text, f"Help doesn't mention the {preset.label} preset"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `... -m pytest tests/test_tray_presets.py tests/test_help_feedback_link.py -q -p no:cacheprovider`
Expected: FAIL (`_current_presets` and `GetPresets` are missing; Help names the old presets).

- [ ] **Step 3: Implement in tray.py**

Delete the `PERFORMANCE_PRESETS` dict, `_PRESET_EXTRA_KEYS`, `_download_cuda_for_most_accurate` and the old `_get_current_preset` / `set_performance_preset` bodies. Add:

```python
    def _current_presets(self):
        """The Performance presets for this computer and language (recommend.py)."""
        from . import recommend
        from .config import load_config
        cfg = load_config()
        return recommend.presets(recommend.effective_language(cfg), recommend.detect_hardware(cfg))

    def _get_current_preset(self) -> str:
        """Id of the preset the settings match, or 'custom'."""
        try:
            from . import recommend
            from .config import load_config
            return recommend.match_preset(load_config(), self._current_presets())
        except Exception:
            return "custom"

    def set_performance_preset(self, preset_id: str):
        """Apply a Performance preset: Recommended, Lightest or Battery saver.

        Recommended on a graphics card runs the same setup as Preferences
        (confirm and download the Vulkan files, then the speed check) and
        uses the processor if the chip is slower. Cancelling the download
        changes nothing. Ids from an older GNOME extension ("balanced",
        "accurate"...) are ignored."""
        if getattr(self, "_updating_preset", False):
            return
        try:
            preset = next((p for p in self._current_presets() if p.id == preset_id), None)
        except Exception as e:
            logger.error(f"Could not work out the presets: {e}")
            preset = None
        if preset is None:
            logger.info(f"Ignoring unknown performance preset {preset_id!r}")
            self._revert_preset_radio()
            return
        try:
            from .config import load_config, save_config
            from .model_helper import is_model_cached_fast, download_model_with_progress
            model, device = preset.model, preset.device
            if device == "vulkan":
                from .vulkan_setup_dialogs import ensure_files, run_speed_check
                if not ensure_files(None, model, confirm=True):
                    self._revert_preset_radio()
                    return
                if not run_speed_check(None, model):
                    device = "cpu"
            if device == "cpu" and not is_model_cached_fast(model):
                downloaded = download_model_with_progress(model, device="cpu", show_confirmation=True)
                if downloaded is None:
                    self._revert_preset_radio()
                    return
                del downloaded
            cfg = load_config()
            cfg.model, cfg.device = model, device
            for key, value in preset.extras:
                setattr(cfg, key, value)
            save_config(cfg)
            from .app import _notify
            try:
                from . import whisper_vulkan as _wv
                _gpu_offered = _wv.is_offered()
            except Exception:
                _gpu_offered = False
            logger.info(f"Applied performance preset: {preset.label} ({model} on {device})")
            _notify("TalkType", preset_notice(preset.label, cfg.model, cfg.device, _gpu_offered))
            self.update_menu_display()
            self._emit_model_changed(cfg.model)
            self.restart_service(None)
        except Exception as e:
            logger.error(f"Failed to apply performance preset: {e}")
```

Replace `_build_performance_submenu`'s loop with:

```python
        submenu = Gtk.Menu()
        self.preset_radios = {}
        preset_group = None
        for preset in self._current_presets():
            label = f"{preset.label} ({preset.description})"
            radio = (Gtk.RadioMenuItem(label=label) if preset_group is None
                     else Gtk.RadioMenuItem(label=label, group=preset_group))
            preset_group = preset_group or radio
            # GTK fires "activate" on the radio being unselected too; act on the selected one.
            radio.connect("activate", lambda w, pid=preset.id: w.get_active() and self.set_performance_preset(pid))
            submenu.append(radio)
            self.preset_radios[preset.id] = radio
```

(keep the separator, the "Custom (via Preferences)" item and the return). In `update_menu_display`, just before `current_preset = self._get_current_preset()` add:

```python
                    for _p in self._current_presets():
                        if _p.id in self.preset_radios:
                            self.preset_radios[_p.id].set_label(f"{_p.label} ({_p.description})")
```

In `TrayAppInstance` add:

```python
                def get_presets(self):
                    """(id, label, description) for the GNOME extension's Performance menu."""
                    return [(p.id, p.label, p.description) for p in self.tray._current_presets()]

                def current_preset(self):
                    return self.tray._get_current_preset()
```

- [ ] **Step 4: Implement in dbus_service.py**

```python
    @dbus.service.method(DBUS_INTERFACE, out_signature='a(sss)')
    def GetPresets(self):
        """The Performance presets for this computer: (id, label, description).
        The GNOME extension builds its menu from this, so it can't drift from
        the tray's."""
        get = getattr(self.app, "get_presets", None)
        return dbus.Array([dbus.Struct(p, signature='sss') for p in (get() if get else [])],
                          signature='(sss)')
```

and in `GetStatus`, before `# Add statistics if available`:

```python
        current = getattr(self.app, "current_preset", None)
        status['preset'] = str(current() if current else "custom")
```

Also update `ApplyPerformancePreset`'s docstring to "Apply a performance preset (recommended/lightest/battery)".

- [ ] **Step 5: Update Help** (`help_dialog.py`). Replace the whole "Performance Mode Presets" paragraph with:

```
<b>Performance Mode Presets</b>
Quick changes from the tray menu (Performance):
• <b>Recommended for this computer:</b> the setup TalkType picks for your graphics card
  and language, usually Parakeet on your graphics card
• <b>Lightest:</b> Whisper Base on the processor, the smallest download and the least work
• <b>Battery saver:</b> Whisper Tiny on the processor, stops after 2 idle minutes
After choosing one, the tray's Device line shows where it really runs.
```

- [ ] **Step 6: Delete the three old preset test files and run everything**

```bash
git rm tests/test_preset_selection.py tests/test_presets_vulkan.py tests/test_preset_dot_parity.py
```

Run the full suite. Expected: all PASS. If another test references `PERFORMANCE_PRESETS` or `_PRESET_EXTRA_KEYS`, update it to `recommend.presets` the same way as the Help test.

- [ ] **Step 7: Commit**

```bash
git add src/talktype/tray.py src/talktype/dbus_service.py src/talktype/help_dialog.py tests/test_tray_presets.py tests/test_help_feedback_link.py
git commit -m "Replace the seven model presets with Recommended, Lightest and Battery saver

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: GNOME extension builds Performance from GetPresets (v15)

**Files:**
- Modify: `gnome-extension/talktype@ronb1964.github.io/extension.js`, `metadata.json`
- Test: `tests/test_extension_presets.py` (new)

**Interfaces:**
- Consumes: D-Bus `GetPresets() -> a(sss)`, `GetStatus()["preset"]`, `ApplyPerformancePreset(s)` (Task 3).
- Produces: the extension's menu always matches the tray's presets.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extension_presets.py
"""The GNOME menu's Performance presets come from the tray (GetPresets).

The extension kept its own copy of the preset table and its own matcher, and
the two drifted (Battery Saver's dot sat on Fastest). Now it asks the tray.
"""
import json
import pathlib

EXT = pathlib.Path(__file__).resolve().parent.parent / "gnome-extension/talktype@ronb1964.github.io"
JS = (EXT / "extension.js").read_text()


def test_interface_declares_getpresets():
    assert '<method name="GetPresets">' in JS
    assert '<arg type="a(sss)" direction="out" name="presets"/>' in JS


def test_no_hard_coded_preset_table():
    assert "PERFORMANCE_PRESETS" not in JS and "PRESET_EXTRA_KEYS" not in JS
    assert "_getCurrentPreset" not in JS


def test_menu_is_built_from_the_tray():
    assert "GetPresetsRemote" in JS
    assert "status.preset" in JS


def test_version_is_15():
    assert json.loads((EXT / "metadata.json").read_text())["version"] == 15
```

- [ ] **Step 2: Run it to verify it fails.**

- [ ] **Step 3: Implement**
  1. In `TalkTypeIface`, after `<method name="GetStatus">...</method>`, add:

```xml
    <method name="GetPresets">
      <arg type="a(sss)" direction="out" name="presets"/>
    </method>
```

  2. Delete the `PERFORMANCE_PRESETS` and `PRESET_EXTRA_KEYS` constants and the `_getCurrentPreset()` method. In `_init`, replace `this._currentExtras = {};` with `this._currentPreset = 'custom';`.
  3. In `_buildMenu`, replace the loop that fills `this._performanceSubMenu` with nothing: keep `this._performanceSubMenu = new PopupMenu.PopupSubMenuMenuItem('Performance'); this._presetItems = {}; this.menu.addMenuItem(this._performanceSubMenu);`. In the existing `this.menu.connect('open-state-changed', ...)` handler, call `this._refreshPresets();` next to `this._refreshHistoryMenu();`.
  4. Add:

```js
    _refreshPresets() {
        // The tray owns the presets (recommend.py): build the submenu from them
        // each time the menu opens, so the two menus can't drift.
        const menu = this._performanceSubMenu.menu;
        this._proxy.GetPresetsRemote((result, error) => {
            menu.removeAll();
            this._presetItems = {};
            const presets = result ? result[0] : null;
            if (error || !presets || presets.length === 0) {
                menu.addMenuItem(new PopupMenu.PopupMenuItem(
                    'Update TalkType to use presets', {reactive: false}));
                return;
            }
            for (const [id, label, description] of presets) {
                const item = new PopupMenu.PopupMenuItem(`${label} (${description})`);
                item.connect('activate', () => this._proxy.ApplyPerformancePresetRemote(id));
                this._presetItems[id] = item;
                menu.addMenuItem(item);
            }
            this._updatePresetSelection(this._currentPreset);
        });
    }
```

  5. In `_updateStatus`, replace the extras loop (`this._currentExtras = {}; for (const key of PRESET_EXTRA_KEYS) {...}`) with:

```js
            // The tray works out which preset is active (recommend.match_preset).
            this._currentPreset = status.preset ? status.preset.deep_unpack() : 'custom';
```

  6. In `_updateMenu`, replace `const currentPreset = this._getCurrentPreset(); this._updatePresetSelection(currentPreset);` with `this._updatePresetSelection(this._currentPreset);`.
  7. `metadata.json`: `"version": 15`.

- [ ] **Step 4: Run the test, then the full suite.** Also run `node --check gnome-extension/talktype@ronb1964.github.io/extension.js` (expected: no output).

- [ ] **Step 5: Commit**

```bash
git add gnome-extension/talktype@ronb1964.github.io/extension.js gnome-extension/talktype@ronb1964.github.io/metadata.json tests/test_extension_presets.py
git commit -m "GNOME extension v15: build Performance from the tray's presets

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The first-run recommendation card

**Files:**
- Modify: `src/talktype/welcome_dialog.py`:
  - `WelcomeDialog.__init__` (hardware, language, height);
  - `_build_dialog` CSS;
  - `_build_optional_features`;
  - new `_build_recommendation` and helpers;
  - remove `_build_cuda_option`;
  - `_pulse_checkboxes`;
  - `run()`;
  - footer label.
- Test: `tests/test_first_run_recommendation.py` (new)

**Interfaces:**
- Consumes: `recommend.detect_hardware`, `system_language`, `language_name`, `LANGUAGES`, `recommend`, `option_states`.
- Produces: `WelcomeDialog.run()` returns, besides the existing keys, `'model'`, `'device'` and `'dictation_language'`. It no longer returns `'download_cuda'` or `'use_vulkan'`. `WelcomeDialog._current_setup() -> recommend.Setup`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_first_run_recommendation.py
"""First run recommends one complete setup instead of asking about CUDA.

The old screen: an unticked "Use your NVIDIA graphics card" box, Full (CUDA,
1.4 GB, preselected) or Light (Vulkan), AMD/Intel never offered, and the model
picked on a later screen. Now one card says what will be set up, and Other
options change it with every choice explained.
"""
import pathlib

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from talktype import recommend as r  # noqa: E402
from talktype import welcome_dialog as wd  # noqa: E402

SRC = (pathlib.Path(wd.__file__)).read_text()


@pytest.fixture
def dialog(monkeypatch):
    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    monkeypatch.setattr(r, "detect_hardware",
                        lambda cfg=None: r.Hardware("NVIDIA GeForce RTX 4070 SUPER", True))
    monkeypatch.setattr(r, "system_language", lambda env=None: "en")
    monkeypatch.setattr(wd, "detect_uinput_access", lambda: (True, ""))
    monkeypatch.setattr(wd, "detect_ydotoold_status", lambda: {"needs_setup": False})
    monkeypatch.setattr(wd, "detect_portaudio_status", lambda: {"needs_install": False})
    d = wd.WelcomeDialog(force_gnome=False)
    yield d
    d.destroy()


def test_card_shows_the_recommendation(dialog):
    s = dialog._current_setup()
    assert (s.model, s.device) == ("parakeet-v3", "vulkan")
    assert "Parakeet on your NVIDIA GeForce RTX 4070 SUPER" in dialog.rec_title.get_text()


def test_changing_the_language_updates_the_card(dialog):
    dialog.lang_combo.set_active_id("ja")
    s = dialog._current_setup()
    assert s.model == "large-v3" and "Whisper Large-v3" in dialog.rec_title.get_text()
    assert not dialog.model_radios["parakeet-v3"].get_sensitive()


def test_unticking_the_graphics_card_uses_the_processor(dialog):
    dialog.gpu_check.set_active(False)
    assert dialog._current_setup().device == "cpu"
    assert "processor" in dialog.rec_title.get_text()


def test_run_result_carries_the_setup(dialog, monkeypatch):
    monkeypatch.setattr(dialog.dialog, "run", lambda: Gtk.ResponseType.OK)
    monkeypatch.setattr(dialog, "_fade_in_dialog", lambda o: None)
    result = dialog.run()
    assert (result["model"], result["device"], result["dictation_language"]) == \
        ("parakeet-v3", "vulkan", "en")
    assert "download_cuda" not in result and "use_vulkan" not in result


def test_first_run_never_mentions_cuda():
    assert "_build_cuda_option" not in SRC
    assert "Download CUDA Libraries" not in SRC
```

- [ ] **Step 2: Run them to verify they fail.**

- [ ] **Step 3: Implement**
  1. In `__init__`, after `self.has_nvidia = ...`, add:

```python
        # What to recommend (recommend.py): the graphics chip and the language.
        from . import recommend as _rec
        try:
            from .config import load_config
            _cfg = load_config()
        except Exception:
            _cfg = None
        self.hardware = _rec.detect_hardware(_cfg)
        self.initial_language = _rec.system_language()
        self._chosen_model = None      # set when the user picks a model in Other options
```

     In the height block, replace `if self.has_nvidia: additional_height += 180  # CUDA section` with `additional_height += 170  # recommendation card`. Initialize `self.gpu_check = None` next to `self.cuda_check = None`, and delete the `self.gpu_vulkan_radio` line.

  2. In the CSS string in `_build_dialog`, append:

```css
            .tt-rec-card {
                border: 2px solid #4a90e2;
                border-radius: 10px;
                padding: 12px 14px;
                background-color: rgba(74, 144, 226, 0.10);
            }
            .tt-rec-tag {
                color: #7fb2f0;
                font-weight: bold;
                font-size: 9pt;
            }
```

  3. In `_build_optional_features`:
     - at the start, after the separator, call `self._build_recommendation(vbox)` when `not self.hotkey_unsupported`;
     - change every `self.has_gnome or self.has_nvidia` condition to `self.has_gnome`;
     - delete the `if self.has_nvidia: self._build_cuda_option(vbox)` call;
     - change the note to `'💡 <i>You can change these anytime in Preferences</i>'`.
  4. Delete `_build_cuda_option` entirely. In `_pulse_checkboxes`, delete the `cuda_check` lines.
  5. Add these methods:

```python
    def _build_recommendation(self, vbox):
        """The "Recommended for your computer" card and Other options.

        The card always shows exactly what will be set up; choices that can't
        work are greyed out with the reason (recommend.option_states)."""
        from . import recommend as rec
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.get_style_context().add_class("tt-rec-card")
        tag = Gtk.Label(xalign=0)
        tag.set_markup("RECOMMENDED FOR YOUR COMPUTER")
        tag.get_style_context().add_class("tt-rec-tag")
        self.rec_title = Gtk.Label(xalign=0)
        self.rec_explanation = Gtk.Label(xalign=0)
        self.rec_explanation.set_line_wrap(True)
        self.rec_download = Gtk.Label(xalign=0)
        self.rec_download.set_opacity(0.75)
        for w in (tag, self.rec_title, self.rec_explanation, self.rec_download):
            card.pack_start(w, False, False, 0)
        vbox.pack_start(card, False, False, 6)

        expander = Gtk.Expander(label="Other options")
        other = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        other.set_margin_start(12)

        lang_row = Gtk.Box(spacing=8)
        lang_row.pack_start(Gtk.Label(label="I dictate in", xalign=0), False, False, 0)
        self.lang_combo = Gtk.ComboBoxText()
        codes = [c for c, _ in rec.LANGUAGES]
        for code, name in rec.LANGUAGES:
            self.lang_combo.append(code, name)
        if self.initial_language not in codes:
            self.lang_combo.append(self.initial_language, rec.language_name(self.initial_language))
        self.lang_combo.set_active_id(self.initial_language)
        lang_row.pack_start(self.lang_combo, False, False, 0)
        other.pack_start(lang_row, False, False, 0)

        model_header = Gtk.Label(xalign=0)
        model_header.set_markup("<b>Speech model</b>")
        other.pack_start(model_header, False, False, 4)
        self.model_radios, self.model_reasons, group = {}, {}, None
        for state in rec.option_states(self.initial_language, self.hardware):
            radio = Gtk.RadioButton.new_from_widget(group)
            group = group or radio
            text = Gtk.Label(xalign=0)
            text.set_line_wrap(True)
            radio.add(text)
            radio.connect("toggled", self._on_model_radio, state.model)
            self.model_radios[state.model] = radio
            self.model_reasons[state.model] = text
            other.pack_start(radio, False, False, 0)
        more = Gtk.Label(xalign=0)
        more.set_markup('<span size="small"><i>More models (Tiny, Base, Medium) are in Preferences.</i></span>')
        other.pack_start(more, False, False, 0)

        where = Gtk.Label(xalign=0)
        where.set_markup("<b>Where it runs</b>")
        other.pack_start(where, False, False, 4)
        if self.hardware.gpu:
            self.gpu_check = Gtk.CheckButton(label=f"Use my graphics card ({self.hardware.gpu_name})")
            self.gpu_check.set_active(True)
            self.gpu_check.set_tooltip_text("Several times faster. TalkType checks it really is "
                                            "faster than your processor before using it.")
            self.gpu_check.connect("toggled", lambda *_: self._refresh_recommendation())
            other.pack_start(self.gpu_check, False, False, 0)
        else:
            other.pack_start(Gtk.Label(label="On this computer's processor", xalign=0), False, False, 0)

        expander.add(other)
        vbox.pack_start(expander, False, False, 0)
        self.lang_combo.connect("changed", lambda *_: self._refresh_recommendation())
        self._refresh_recommendation()

    def _language(self):
        return self.lang_combo.get_active_id() or self.initial_language

    def _use_gpu(self):
        return bool(self.gpu_check and self.gpu_check.get_active())

    def _current_setup(self):
        from . import recommend as rec
        return rec.recommend(self._language(), self.hardware,
                             model=self._chosen_model, use_gpu=self._use_gpu())

    def _on_model_radio(self, radio, model):
        if radio.get_active() and not getattr(self, "_syncing", False):
            self._chosen_model = model
            self._refresh_recommendation()

    def _refresh_recommendation(self):
        """Update the card and the greyed choices from recommend.py."""
        from . import recommend as rec
        setup = self._current_setup()
        name = rec.language_name(self._language())
        self.rec_title.set_markup(f"<b>{GLib.markup_escape_text(setup.title)}</b>")
        self.rec_explanation.set_markup(
            f"{GLib.markup_escape_text(setup.explanation)} For <b>{GLib.markup_escape_text(name)}</b>.")
        self.rec_download.set_text(setup.download_text)
        self._syncing = True
        try:
            for state in rec.option_states(self._language(), self.hardware):
                radio, text = self.model_radios[state.model], self.model_reasons[state.model]
                radio.set_sensitive(state.available)
                note = state.description if state.available else state.reason
                mark = " (recommended)" if state.model == setup.model else ""
                text.set_markup(f"<b>{state.label}</b>{mark}, {state.size}\n"
                                f'<span size="small">{GLib.markup_escape_text(note)}</span>')
                if state.model == setup.model:
                    radio.set_active(True)
        finally:
            self._syncing = False
```

  6. In `run()`, replace the `if self.cuda_check:` block with:

```python
        if hasattr(self, "rec_title"):
            setup = self._current_setup()
            result['model'] = setup.model
            result['device'] = setup.device
            result['dictation_language'] = self._language()
```

  7. In `_build_footer`, change the primary button's label from `"Let's Go!"` to `"Set it up"`. If a test asserts the old label, update it.

- [ ] **Step 4: Run the new tests and the full suite.** Fix any older test that built `WelcomeDialog(force_nvidia=True)` and expected `cuda_check` or `gpu_vulkan_radio`: it should now assert the recommendation card instead.

- [ ] **Step 5: Commit**

```bash
git add src/talktype/welcome_dialog.py tests/test_first_run_recommendation.py
git commit -m "First run: one recommended setup for this computer, with Other options

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: First-run setup applies the recommendation, with no later model picker

**Files:**
- Modify: `src/talktype/welcome_dialog.py`:
  - `show_welcome_and_install`;
  - `show_tips_and_features_dialog` (remove the model section and return None);
  - delete `_large_v3_without_nvidia_message` and its test file `tests/test_large_v3_first_run_message.py`, since the picker that used it is gone.
- Test: `tests/test_first_run_flow.py` (new)

**Interfaces:**
- Consumes: `WelcomeDialog.run()` keys `model`, `device`, `dictation_language` (Task 5); `_setup_vulkan_engine_first_run()`, `_download_vulkan_model_first_run(model) -> bool`, `_vulkan_speed_check_first_run(model) -> bool` (existing); `model_helper.download_model_with_progress`, `is_model_cached`.
- Produces: `_apply_first_run_setup(result) -> None`, which saves `model`, `device`, `dictation_language` and `recommend_notice_shown=True`, then downloads.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_first_run_flow.py
"""After the welcome card, setup downloads exactly what it showed."""
import types

import pytest

from talktype import welcome_dialog as wd


@pytest.fixture
def env(monkeypatch):
    cfg = types.SimpleNamespace(model="parakeet-v3", device="cpu", dictation_language="",
                                recommend_notice_shown=False)
    calls = []
    monkeypatch.setattr("talktype.config.load_config", lambda: cfg)
    monkeypatch.setattr("talktype.config.save_config", lambda c: calls.append(("save", c.model, c.device)))
    monkeypatch.setattr(wd, "_setup_vulkan_engine_first_run", lambda: calls.append(("engine",)))
    monkeypatch.setattr(wd, "_download_vulkan_model_first_run", lambda m: calls.append(("vk", m)) or True)
    monkeypatch.setattr(wd, "_vulkan_speed_check_first_run", lambda m: calls.append(("speed", m)) or True)
    monkeypatch.setattr("talktype.model_helper.is_model_cached", lambda m: False)
    monkeypatch.setattr("talktype.model_helper.download_model_with_progress",
                        lambda m, **k: calls.append(("cpu", m)) or object())
    return cfg, calls


def test_graphics_card_setup(env):
    cfg, calls = env
    wd._apply_first_run_setup({"model": "parakeet-v3", "device": "vulkan", "dictation_language": "en"})
    assert ("engine",) in calls and ("vk", "parakeet-v3") in calls and ("speed", "parakeet-v3") in calls
    assert (cfg.model, cfg.device, cfg.dictation_language) == ("parakeet-v3", "vulkan", "en")
    assert cfg.recommend_notice_shown is True
    assert not any(c[0] == "cpu" for c in calls)


def test_slower_graphics_falls_back_to_the_processor_model(env, monkeypatch):
    cfg, calls = env
    monkeypatch.setattr(wd, "_vulkan_speed_check_first_run", lambda m: False)
    wd._apply_first_run_setup({"model": "parakeet-v3", "device": "vulkan", "dictation_language": "en"})
    assert cfg.device == "cpu" and ("cpu", "parakeet-v3") in calls


def test_processor_setup(env):
    cfg, calls = env
    wd._apply_first_run_setup({"model": "small", "device": "cpu", "dictation_language": "ja"})
    assert ("cpu", "small") in calls and not any(c[0] in ("engine", "vk") for c in calls)
    assert (cfg.model, cfg.device, cfg.dictation_language) == ("small", "cpu", "ja")


def test_tips_dialog_no_longer_picks_a_model():
    import pathlib
    src = pathlib.Path(wd.__file__).read_text()
    assert "Choose Your Starting Model" not in src
```

- [ ] **Step 2: Run them to verify they fail.**

- [ ] **Step 3: Implement**
  1. Add `_apply_first_run_setup(result)`. Its body is the existing model-download block of `show_welcome_and_install` (from `selected_model = ...` to the end of the emergency-fallback `except`), with these changes:
     - it starts by saving `config.model = result["model"]`, `config.device = result["device"]`, `config.dictation_language = result.get("dictation_language", "")`, `config.recommend_notice_shown = True`;
     - when `device == "vulkan"` it calls `_setup_vulkan_engine_first_run()` before `_download_vulkan_model_first_run(...)`;
     - `selected_model` is `result["model"]`.
  2. In `show_welcome_and_install`:
     - `download_cuda` is gone. The unified download dialog runs only for `install_extension`, so pass `cuda=False`.
     - The `if result.get('use_vulkan'): _setup_vulkan_engine_first_run()` block is removed.
     - After the hotkey test it calls `show_tips_and_features_dialog(extension_installed=...)` (tips only), then `_apply_first_run_setup(result)` when `'model' in result`.
  3. In `show_tips_and_features_dialog`:
     - delete everything from `# Model selection section` (the separator `sep_model`) through the model description label;
     - delete the `_on_onboarding_model_changed` and `get_combo_model_id` helpers;
     - the button label becomes "Continue" (no download text);
     - the function returns `None`.
  4. Delete `_large_v3_without_nvidia_message` and run `git rm tests/test_large_v3_first_run_message.py`.

- [ ] **Step 4: Run the full suite.** If `tests/test_config.py::test_first_run_and_preferences_recommend_parakeet` asserts welcome-picker strings that no longer exist, change it to assert `recommend.recommend("en", recommend.Hardware(None)).model == "parakeet-v3"` and keep its Preferences checks.

- [ ] **Step 5: Commit**

```bash
git add src/talktype/welcome_dialog.py tests/test_first_run_flow.py tests/test_config.py
git commit -m "First run downloads exactly the setup the card showed

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The one-time notice for existing users

**Files:**
- Modify: `src/talktype/tray.py` (`maybe_show_recommend_notice`, scheduled at start)
- Test: `tests/test_recommend_notice.py` (new)

**Interfaces:**
- Consumes: `recommend.differs_from_recommendation(cfg, hw)`, `recommend.detect_hardware(cfg)`, `cuda_helper.is_first_run()`, `app._notify`.
- Produces: `recommend_notice_text(setup) -> str` and `maybe_show_recommend_notice() -> bool` (both module-level in tray.py; returns False so it can be a GLib timeout).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_recommend_notice.py
"""Existing users hear once that there's a better setup, only if there is."""
import types

import pytest

from talktype import recommend as r
from talktype import tray

NVIDIA = r.Hardware("NVIDIA GeForce RTX 4070 SUPER", True)


@pytest.fixture
def env(monkeypatch):
    cfg = types.SimpleNamespace(model="small", device="cpu", recommend_notice_shown=False,
                                dictation_language="en", language_mode="auto", language="",
                                vulkan_slower=False)
    notes, saved = [], []
    monkeypatch.setattr("talktype.config.load_config", lambda: cfg)
    monkeypatch.setattr("talktype.config.save_config", lambda c: saved.append(c.recommend_notice_shown))
    monkeypatch.setattr("talktype.app._notify", lambda t, b: notes.append(b))
    monkeypatch.setattr("talktype.cuda_helper.is_first_run", lambda: False)
    monkeypatch.setattr(r, "detect_hardware", lambda cfg=None: NVIDIA)
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    return cfg, notes, saved


def test_shown_once_when_the_setup_differs(env):
    cfg, notes, saved = env
    tray.maybe_show_recommend_notice()
    assert len(notes) == 1 and "Parakeet on your NVIDIA GeForce RTX 4070 SUPER" in notes[0]
    assert "Performance" in notes[0] and saved == [True]
    cfg.recommend_notice_shown = True
    tray.maybe_show_recommend_notice()
    assert len(notes) == 1


def test_silent_when_already_on_the_recommendation(env):
    cfg, notes, saved = env
    cfg.model, cfg.device = "parakeet-v3", "vulkan"
    tray.maybe_show_recommend_notice()
    assert notes == [] and saved == [True]


def test_never_on_first_run_or_flatpak(env, monkeypatch):
    cfg, notes, saved = env
    monkeypatch.setattr("talktype.cuda_helper.is_first_run", lambda: True)
    tray.maybe_show_recommend_notice()
    monkeypatch.setattr("talktype.cuda_helper.is_first_run", lambda: False)
    monkeypatch.setenv("FLATPAK_ID", "io.github.ronb1964.TalkType")
    tray.maybe_show_recommend_notice()
    assert notes == []


def test_notice_wording():
    s = r.recommend("en", NVIDIA)
    assert tray.recommend_notice_text(s) == (
        "There's a better setup for this computer: Parakeet on your NVIDIA GeForce "
        "RTX 4070 SUPER. Choose Performance → Recommended for this computer in the "
        "TalkType menu to switch.")
```

- [ ] **Step 2: Run them to verify they fail.**

- [ ] **Step 3: Implement** (module level in tray.py, after `preset_notice`):

```python
def recommend_notice_text(setup):
    return (f"There's a better setup for this computer: {setup.title}. Choose Performance "
            "→ Recommended for this computer in the TalkType menu to switch.")


def maybe_show_recommend_notice():
    """Once, on the first start after updating: tell existing users when the
    recommended setup differs from theirs (Ron, 2026-10-06). Never on first run
    (first run sets recommend_notice_shown) or the Flatpak. Returns False so it
    can run as a one-shot GLib timeout."""
    try:
        import os as _os
        from . import recommend
        from .config import load_config, save_config
        from .cuda_helper import is_first_run
        if _os.environ.get("FLATPAK_ID") or is_first_run():
            return False
        cfg = load_config()
        if cfg.recommend_notice_shown:
            return False
        better = recommend.differs_from_recommendation(cfg, recommend.detect_hardware(cfg))
        if better is not None:
            from .app import _notify
            _notify("TalkType", recommend_notice_text(better))
            logger.info(f"Told the user about the recommended setup: {better.title}")
        cfg.recommend_notice_shown = True
        save_config(cfg)
    except Exception as e:
        logger.debug(f"Recommended-setup notice skipped: {e}")
    return False
```

In `DictationTray.__init__`, after `GLib.timeout_add_seconds(1, self.update_status_and_menu)`, add:

```python
        # Once after updating: point existing users at the recommended setup.
        GLib.timeout_add_seconds(15, maybe_show_recommend_notice)
```

- [ ] **Step 4: Run the tests and the full suite.**

- [ ] **Step 5: Commit**

```bash
git add src/talktype/tray.py tests/test_recommend_notice.py
git commit -m "Tell existing users once when there's a better setup for their computer

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Verify on screen and in the VMs

**Files:** none changed unless a defect is found (fix it in the owning task's files and commit separately).

- [ ] **Step 1: Throwaway-profile screenshots on KDE** (HOME pointed at the scratchpad, `env -u GDK_BACKEND`, `spectacle -b -n -a`):
  - (a) the welcome card collapsed with NVIDIA;
  - (b) Other options expanded;
  - (c) the language switched to Japanese;
  - (d) no GPU (monkeypatch `recommend.detect_hardware` to `Hardware(None)` in the launcher script).

  Compare them with mockup A in `.superpowers/brainstorm/*/content/other-options-v2.html`.
- [ ] **Step 2: Restart Ron's dev TalkType** and check:
  - the tray Performance menu shows the three presets;
  - "Recommended for this computer" carries the radio dot (Ron is on parakeet-v3/vulkan);
  - no update notice appears, because his setup matches.
- [ ] **Step 3: GNOME VM (ubuntu26.04)**: install extension v15 with the patched build as in the hotkey test. Check that the Performance submenu lists the three presets from GetPresets and the dot follows a preset change.
- [ ] **Step 4: Mint VM (X11, no NVIDIA)**: the card says "Parakeet on this computer's processor" or names the VM's graphics; a preset switch works.
- [ ] **Step 5: Run the full suite one final time** and report the count.

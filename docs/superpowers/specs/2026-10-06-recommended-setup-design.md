# Recommended setup: first run, presets and the update notice

Date: 2026-10-06. Status: approved by Ron in conversation (Phase 2 of the
settings UX work; Phase 1 shipped as c39514e and earlier).

## Problem

How fast and accurate TalkType is depends on three controls (model,
device, preset) that only work in certain combinations, and nothing
recommends a combination for the user's computer. On first run:

- the graphics card is opt-in;
- NVIDIA defaults to a 1.4 GB CUDA download that Parakeet can't use;
- AMD and Intel cards are never offered;
- the model is picked on a later screen, separately from the device.

The tray presets are named after models and often do something other
than their label says. Ron, the developer, ended up on Parakeet on the
processor with an idle RTX 4070 Super.

## Goal

A new user ends up on the best setup for their computer with one click,
without knowing what a model, CUDA or Vulkan is:

- English or one of Parakeet's 24 other European languages, with a
  usable graphics card: **Parakeet on the graphics card (Vulkan)**.
- Same languages, no usable graphics card: **Parakeet on the processor**.
- Any other language: **Whisper Large-v3 on the graphics card**, or
  **Whisper Small on the processor** without one.

Everything stays changeable in Preferences. Existing users' settings are
never changed without them choosing to.

## Decisions (Ron, 2026-10-06)

1. **Language** is guessed from the computer's language setting and shown
   in the recommendation ("For English, change"). Changing it updates the
   recommendation.
2. **A usable graphics card is used by default**, through Vulkan (24 MB,
   any brand). The speed check still decides; if the processor is faster
   it quietly stays on the processor.
3. **CUDA lives in Preferences only.** First run never mentions it.
   Phasing CUDA out is to be revisited after Vulkan has a few releases
   behind it.
4. **Presets** become three outcomes: Recommended for this computer,
   Lightest, Battery saver. "Most accurate" and "Fastest" were dropped
   because they matched Recommended on almost every computer.
5. **Existing users** get one notification on the first start after
   updating, and only if their setup differs from the recommendation.
6. **First-run layout** is mockup A: one recommendation card with a "Set
   it up" button, and "Other options" opening in place.

## What users see

### First run

The welcome screen keeps the short introduction and replaces the
"Optional Features" GPU section with the recommendation card:

> RECOMMENDED FOR YOUR COMPUTER
> **Parakeet on your NVIDIA RTX 4070 Super**
> Very accurate and nearly instant. For **English** (change)
> About 700 MB, downloaded once.
> [Set it up]   ▸ Other options

"Other options" opens in place with three sections:

- **I dictate in:** a language dropdown, pre-filled from the system locale.
- **Speech model:**
  - Parakeet (recommended), 670 MB: "The most accurate for English and 24
    European languages. Fast even without a graphics card."
  - Whisper Small, 250 MB: "Knows 99 languages. A good choice on an older
    or slower computer."
  - Whisper Large-v3, about 3 GB on the processor or 1 GB on the graphics
    card: "Whisper's most accurate, for languages Parakeet doesn't know.
    Needs a graphics card."
  - A note says Tiny, Base and Medium are in Preferences.
- **Where it runs:** "Use my graphics card (<name>)", ticked when a usable
  one is found: "Several times faster. TalkType checks it really is faster
  than your processor before using it." Without a usable graphics card the
  box is absent and the section reads "On this computer's processor".

Rules:

- The card always describes exactly what "Set it up" will do. Every change
  in Other options updates its title, explanation and download size.
- A choice that can't work is greyed out with the reason, never hidden:
  - Parakeet when the language isn't one of its 25: "Doesn't understand
    <language>."
  - Large-v3 without a usable graphics card: "Needs a graphics card."
- Changing the language re-runs the recommendation only while the user
  hasn't picked a model themselves. Once they have, a choice that stops
  working (Parakeet with Japanese) switches to the recommended model and
  the card says why.

After "Set it up": the existing hotkey test, then the downloads (Vulkan
engine, model and speed check when on the graphics card; otherwise the
processor model), then the existing Ready screen. The later "Choose Your
Starting Model" section of the tips dialog is removed; the tips stay.

### Tray Performance menu (and the GNOME menu)

| Preset | What it sets |
|---|---|
| Recommended for this computer | Exactly what first run would recommend now |
| Lightest | Whisper Base on the processor (never the same as Recommended, which is Small without a graphics card for non-European languages) |
| Battery saver | Whisper Tiny on the processor, auto-timeout on, 2 minutes |

The greyed "Custom (via Preferences)" line stays. The radio dot shows the
preset whose model, device and extras match the current settings, and
Custom otherwise. Choosing Recommended when it means the graphics card
runs the same Vulkan setup as Preferences (confirm, download, speed check)
before switching. The preset notification (Phase 1's preset_notice) says
where it runs.

### Existing users

On the tray's first start of a version with this feature, if the current
model or device differs from the recommendation, one desktop notification:

> There's a better setup for this computer: <recommendation title>.
> Choose Performance → Recommended for this computer in the TalkType menu
> to switch.

A config flag records that it was shown, and it is never shown again. It
is not shown on first run (no hotkey yet), on the Flatpak, or when the
setup already matches.

## Design

### New module `recommend.py` (pure logic, no GTK)

- `Hardware`: facts about the computer.
  - `gpu_name`: display name, or None when there is no usable graphics
    chip.
  - `vulkan_usable` (whisper_vulkan.is_offered()).
  - `has_nvidia`.
  - It is built by `detect_hardware()`, which takes the NVIDIA name from
    nvidia-smi and AMD/Intel names from lspci, with "your graphics card" as
    the fallback. It never raises.
- `system_language()`: the ISO 639-1 code from the locale (`LANG`,
  `LC_ALL`, `LC_MESSAGES`), defaulting to "en".
- `Setup(model, device, title, explanation, download_text)`: frozen.
- `recommend(language, hw, model=None, use_gpu=None)`: the setup for this
  computer. `model` and `use_gpu` override the recommendation (Other
  options) and are validated: a choice that can't work is replaced and the
  explanation says why.
- `option_states(language, hw)`: for each offered model, whether it's
  available and the reason if not. This drives the greyed rows.
- `presets(language, hw)`: an ordered list of `Preset(id, label,
  description, model, device, extras)` for "recommended", "lightest" and
  "battery". The ids are stable strings.
- `differs_from_recommendation(cfg, language, hw)`: drives the update
  notice.

Language (`effective_language(cfg)`), in this order:
1. the config field `dictation_language` (new, default ""), set at first run;
2. otherwise a language picked by hand in Preferences (`language_mode`
   "manual" + `language`), so an existing Japanese Whisper setup isn't
   switched to Parakeet;
3. otherwise `system_language()`.

Whisper's own `language` and `language_mode` settings are unchanged.

A weak graphics chip: when the speed check finds the processor faster,
the new config flag `vulkan_slower` is set (and cleared when the graphics
chip wins). `detect_hardware(cfg)` then reports no usable graphics chip,
so the recommendation, the Recommended preset and the update notice stop
proposing it.

### First run (`welcome_dialog.py`)

- `_build_optional_features`' GPU section is replaced by
  `_build_recommendation(...)`, which renders the card and Other options
  from `recommend()` and `option_states()`.
- `run()` returns `{"model", "device", "dictation_language"}` in place of
  `download_cuda` / `vulkan_light`.
- `show_welcome_and_install` saves those and, after the hotkey test,
  downloads:
  - device vulkan: `_setup_vulkan_engine_first_run`, then
    `_download_vulkan_model_first_run`, then `_vulkan_speed_check_first_run`,
    falling back to the processor model;
  - processor: the existing model download.
  - CUDA is never downloaded at first run.
- `show_tips_and_features_dialog` loses its model picker.
- First-run Parakeet on Vulkan downloads only the graphics copy. If the
  graphics card later fails, the processor copy downloads on demand
  through the existing fallback, with its progress dialog.

### Presets (`tray.py`, `dbus_service.py`, `extension.js`)

- `PERFORMANCE_PRESETS` and `_PRESET_EXTRA_KEYS` are replaced by
  `recommend.presets()`, computed when the menu is built or refreshed.
- `set_performance_preset(id)` applies a preset's model, device and extras.
  On a Vulkan device it uses `vulkan_setup_dialogs.set_up` (confirm,
  download, speed check) and stays on the processor if that declines.
- An old preset id (from an older GNOME extension) is ignored with a log
  line, never treated as an error.
- New D-Bus method `GetPresets() -> a(sss)` returns (id, label,
  description). `GetStatus` gains `preset` (the active id, or "custom").
- The extension builds its Performance submenu from GetPresets, refreshed
  on every menu open, and marks the active one from `status.preset`. It
  drops its hard-coded PERFORMANCE_PRESETS, so the two menus can't drift.
  The extension version goes to 15. With a TalkType too old to have
  GetPresets, the submenu shows one disabled line, "Update TalkType to use
  presets".

### Update notice (`tray.py`)

- At tray start, after the service is up and not on first run or the
  Flatpak: if `recommend_notice_shown` (new config flag) is False and
  `differs_from_recommendation(...)` is True, show the notification. In
  either case, set the flag to True.

## Error handling

- Hardware detection or locale failures fall back to "no usable graphics
  card" and English. They never block setup.
- A failed download, speed check or engine start falls back to the
  processor, as today, with the existing notices.
- Recommended on a computer whose graphics card was removed recomputes
  and lands on the processor.

## Testing

- `recommend.py`: table-driven tests across NVIDIA, AMD/Intel and no
  graphics card × English, Ukrainian and Japanese × overrides. Also locale
  parsing, presets per hardware, and differs_from_recommendation.
- First-run and tray code: unit tests with fake hardware and recommend()
  results. A source check that first run never offers CUDA.
- D-Bus: GetPresets, the preset in GetStatus, and the unknown-id
  fallback.
- On screen:
  - throwaway-profile screenshots of the card collapsed and expanded,
    English and Japanese, with a GPU and without;
  - the Ubuntu VM for the GNOME menu (extension v15);
  - the Mint VM for X11;
  - the fresh-start AppImage checklist before release.

## Out of scope

- Phasing out CUDA (decision 3).
- Recommendations based on how fast the computer is beyond the GPU speed
  check.
- A Flatpak-specific first run. The Flatpak shows the same card through
  the shared welcome_dialog code, but `detect_hardware()` reports no
  usable graphics card there (FLATPAK_ID set: the sandbox has no Vulkan
  engine). So it always recommends Parakeet on the processor, or Whisper
  Small for other languages. Its hotkey steps are unchanged.

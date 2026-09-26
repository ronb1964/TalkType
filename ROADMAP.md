# TalkType Roadmap

Future features, improvements, and expansion ideas. Check off items as they're implemented.

Status markers: `[x]` shipped · `[~]` partly done, see note · `[ ]` not started.

---

## Custom Commands

- [x] Quoted replacement text — if a custom command's replacement is wrapped in quotes (e.g., `"/btw "`), inject it exactly as written, bypassing all normalization (no auto-capitalization, no punctuation changes). Unquoted replacements continue to flow through normalization as today. Implementation: detect quoted values in `_apply_custom_commands()`, protect them with placeholder tokens before `normalize_text()` runs, restore after. Update tooltip on the replacement field in Preferences, the Help dialog, and the README to explain the quoted syntax.
- [ ] Auto-reload custom commands when edited — currently the Preferences Commands tab tells the user "Restart the dictation service for changes to take effect." Should reload `_custom_commands` in app.py automatically (e.g., file-watch on the config or a D-Bus signal from prefs → app) so edits take effect immediately. Removes a friction point users hit every time they touch this list.
- [ ] Importable preset packs of custom commands — a "Linux developer" pack (`why do tool` → `ydotool`, `appy mage` → `AppImage`, `dee bus` → `D-Bus`, etc.), a "Claude Code user" pack with keywords, a "general English" pack with common Whisper trip-ups. Users could install a pack from a "Browse Packs" button in Preferences instead of building their list from scratch. Could grow into a community PR-driven library of shared packs.

## Transcription & AI

*The items marked (2026-09 research) come from a competitive and speech-engine survey done on 2026-09-25. The full write-up is in Obsidian: "TalkType/2026-09-25 - Competitive landscape and direction research". They are listed in priority order.*

- [x] **(2026-09 research) Parakeet as an optional engine.** Priority 1. **Shipped in 0.8.0.** It is `parakeet-v3` in the model list; see `parakeet_engine.py`. Also a "Fast & Accurate" Performance preset in both the tray and the GNOME extension (extension version bumped to 10).
  - What: NVIDIA Parakeet TDT 0.6B v3, run through `onnx-asr`. Keep faster-whisper as the default.
  - Why: it is more accurate than Whisper large-v3 (6.3% vs ~7.4% WER) and several times faster on CPU. CPU users are capped at "medium" today, so they gain the most. Handy, Voxtype, OpenWhispr, hyprwhspr and Vocalinux already offer it.
  - Limits: 25 European languages only, so it can't replace Whisper. The license is CC-BY-4.0, so add an attribution line in About.
  - Size: `onnxruntime` 1.23.2 is already in the AppImage (faster-whisper depends on it), so the AppImage grows by only a few MB. onnx-asr supports Python 3.10 with onnxruntime < 1.24, which matches what we bundle.
  - Model: ~670 MB int8 (`istupakov/parakeet-tdt-0.6b-v3-onnx`), downloaded at runtime like the Whisper models.
  - Nothing is lost: TalkType doesn't use Whisper's `initial_prompt`, which Parakeet lacks.
- [ ] **(2026-09 research) AMD/Intel GPU acceleration via Vulkan.** Priority 2.
  - What: whisper.cpp's Vulkan backend through `pywhispercpp`, built with `GGML_VULKAN=1`. The PyPI wheel is CPU-only, so we would ship our own build.
  - Why: GPU acceleration is NVIDIA-only today. Vulkan reports up to 12x on integrated AMD/Intel graphics, and Voxtype, Vocalinux and hyprwhspr already advertise it.
  - Not ROCm: CTranslate2's ROCm build needs several GB of system ROCm, which is not realistic for AppImage users.
  - Cost: models use the GGML format, a separate download path.
- [x] **(2026-09 research) Optional offline AI cleanup.** Priority 3. **Shipped in 0.9.0** as Dictation Cleanup: plain rules for um/uh and stutters (`cleanup.py`), plus optional AI for self-corrections only (`ai_cleanup.py`: llama.cpp + Qwen2.5-1.5B, downloaded on enable). Every AI answer passes a strict edit check. The original plan below (whole-dictation cleanup) proved too slow on CPU and too eager to reword.
  - What: removes filler words ("um", "uh") and resolves self-corrections ("at 3, no wait, 4" → "at 4"). Every paid app has this, and Windows Fluid Dictation and Gboard now give it away free.
  - How: a 0.6–1.7B GGUF model (e.g. Qwen3) through llama.cpp. Expect about 0.5–2 s per sentence on a modern CPU.
  - Off by default. Show the download size, keep a raw-vs-cleaned toggle, and keep the original text in history. Optionally allow the user's own Ollama.
  - Superwhisper's S1-mini has a custom license; check it before using it.
- [x] Optional transcription history (2026-09 research, priority 4). **Shipped in 0.8.0:** "Recent Dictations ▸" in the tray and the GNOME extension, stored in RAM only (`history.py`, XDG_RUNTIME_DIR). Originally planned as the last 10-20 dictations, click to copy or re-paste from the tray. Handy, hyprwhspr and OpenWhispr have it.
- [ ] (2026-09 research) Personal dictionary: words Whisper keeps getting wrong. For Whisper, pass them as `hotwords`/`initial_prompt` and add a fuzzy-replacement table. Parakeet only gets the replacement table.
- [x] (2026-09 research) Auto-stop on silence in toggle mode. **Shipped in 0.10.0**: `silence.py`, an RMS-vs-learned-noise-floor detector that only decides when to stop and trims only the measured silent tail (it never re-enables vad_filter). Off by default; Preferences → General, under the Toggle Hotkey. It is armed per recording by a **double-tap** of the toggle key (a second tap within 0.4 s, with a high confirmation beep), so a single tap stays a plain toggle for long dictation with thinking pauses. Pause/resume is not done.
- [ ] (2026-09 research) Per-app profiles keyed on the window class only (cleanup on/off, paste mode). **No screen reading or screenshots**: Wispr Flow's screenshot-upload scandal made "nothing leaves your machine" a selling point.
- [ ] (2026-09 research) Later: streaming live preview (Moonshine v2 streaming or Nemotron streaming via sherpa-onnx), and a voice "command mode" that rewrites selected text (needs a 3–4B model).

- [x] Silence auto-stop (VAD) with configurable end-of-speech timeout (shipped in 0.10.0, see above) — note: Silero VAD pre-filtering was deliberately **disabled** (`vad_filter=False`) in v0.5.16 because it trimmed speech onsets after pauses. Any auto-stop feature must be built on a separate timer, not by re-enabling that filter.
- [x] Language auto-detect / multilingual models — `language_mode` (auto/manual) in config and Preferences; empty `language` means auto-detect.
- [ ] Language quick switch in tray menu for multilingual users — the setting exists, but only in Preferences. Not in the tray or GNOME menus.
- [ ] Confidence threshold control — filter low-quality transcriptions from background noise
- [ ] Dictation templates — voice-activated templates (e.g., "compose email" inserts email structure)
- [x] Time format normalization — post-process transcribed times like "5 p. m." or "5. 30 p. m." into clean formats like "5 PM" or "5:30 PM". Implemented as `_RE_TIME_FORMAT` / `_fix_time_ampm`. Reordered on 2026-08-03: it used to run *after* capitalization, so "meet at 9 a. m. tomorrow" came out "9 AM Tomorrow".
- [ ] Empty transcription indicator — visual/audio feedback when no speech detected

## Audio

- [ ] Different beep sounds — selectable audio feedback styles
- [ ] Beep volume control
- [ ] Custom sound files for start/stop feedback
- [ ] Background noise detection — warn if environment is too noisy
- [ ] Automatic mic selection — switch to best available mic
- [ ] Multi-microphone quick switcher in tray menu
- [~] Live audio level indicator — the floating recording indicator has a live level (`recording_indicator.set_audio_level`), and Preferences has a mic test meter. Neither is in the **GNOME panel**, which is what this item meant.

## UI Improvements

- [ ] Session statistics — words transcribed, recording time, characters typed, average WPM
- [ ] Waveform visualization during recording
- [ ] Custom symbolic icon for TalkType branding (mic with "T" badge or speech bubble)
- [ ] Native Wayland positioning via gtk-layer-shell
- [x] Keyboard shortcuts reference — hotkeys are documented in the Help dialog, reachable from both the tray and GNOME menus.
- [~] Voice commands quick access with test feature — the quick-reference dialog exists (`voice_commands_dialog.py`, Ctrl+Alt+V). The **test feature** (try a command and see the result) is still outstanding.
- [ ] Glassmorphism dialog effects — frosted glass blur backgrounds
- [ ] Animated state transitions and loading indicators

## Per-App & Context Features

- [ ] Per-app dictation profiles — different hotkeys/models per application
- [ ] **Auto-disable in password fields and sensitive inputs** — the detection is written (`atspi_helper.py` reads the AT-SPI `password text` role into `context.is_password`), but two things stand between that and the feature:
  1. It is only used to *decline the AT-SPI insertion method* and fall back to typing — the text still gets typed into the password field.
  2. `_determine_injection_method()` returns `use_atspi=False` on every path, so the whole AT-SPI module is currently unreachable.

  Worth raising in priority: TalkType types into whatever holds focus, with no exception for password inputs.
- [ ] Auto-pause detection when switching apps
- [ ] Temporary "pause dictation" mode via tray
- [ ] Workspace awareness — only activate on certain workspaces

## GNOME Extension — Advanced

- [ ] Real cursor position tracking via D-Bus for accurate indicator placement
- [ ] Follow-cursor mode — indicator moves as cursor moves
- [ ] Active text field detection — position indicator near input focus
- [ ] Quick Settings integration — native toggle in GNOME Quick Settings panel
- [ ] Multi-monitor support — know which monitor cursor is on
- [ ] Screen edge detection — prevent indicator from going off-screen
- [x] Check for Updates in GNOME extension menu via D-Bus
- [ ] Activities search integration
- [ ] Publish extension to extensions.gnome.org

## Settings Management

- [ ] Backup settings — export config, custom commands, and preferences to a file
- [ ] Restore settings — import a previously saved backup to restore your setup
- [ ] Settings accessible from Preferences (Backup / Restore buttons)

> Raised in priority by the 2026-08-03 review. Every recovery path added for
> config corruption depends on a single `.bak` sitting beside the file it
> protects — same directory, same disk, same permissions. A real export gives
> the user somewhere else to restore from.

## First-Run & Onboarding

- [x] Guided `/dev/uinput` permission setup with pkexec one-click fix
- [ ] Automated end-to-end typing test on first run to verify text injection works — the hotkey test exists; an injection test does not.
- [x] Graceful clipboard fallback — "copy to clipboard, press Ctrl+V" when ydotool unavailable

## Update System

- [x] Auto-check for updates — once per day, via `should_check_today()`, five seconds after tray launch. Note: this is a one-shot at startup, so an always-on machine that never restarts TalkType won't re-check on its own until the next launch. Making the timer recurring (hourly, still date-gated to daily) would close that gap — deferred until someone asks.
- [x] Install-type-aware updates (0.7.1) — `get_install_type()` picks the right update method: `.deb`/`.rpm` install the new package via `pkexec` (password prompt, through the system package manager), AppImage swaps in place, AUR points to the AUR helper, Flatpak/dev show instructions. Never downloads+runs an AppImage on a package install (the old `libfuse.so.2` failure). Clean detached restart after a package update.
- [x] Update UX unified across the GTK tray and GNOME extension — both route to the same in-app result dialog; the extension no longer opens Preferences on top of it.

## Security

- [ ] Optional modifier requirement (e.g., Ctrl+F8) to prevent accidental capture — the combo machinery already exists for the Voice Commands hotkey (`_check_modifiers_held`); it just isn't offered for the record hotkeys.

## Distribution & Packaging

- [x] AUR — `talktype-appimage` is published and current. `aur/` holds the packaging sources; `aur-repo/` is the untracked publishing clone (`ssh://aur@aur.archlinux.org/talktype-appimage.git`). Updating a release means bumping `pkgver` and `sha256sums` in both, then committing and pushing `aur-repo`. Note there is no `makepkg` on this machine, so `.SRCINFO` is maintained by hand and must be kept in step with the PKGBUILD.
- [x] `.deb` packaging — `build-deb.sh`, validated on real Ubuntu 22.04 and 26.04 (GNOME).
- [x] `.rpm` packaging — `build-rpm.sh`, validated on Fedora GNOME and Fedora KDE VMs. Both are built from the same AppDir the AppImage uses, so a fix in `container-build.sh` reaches all three.
- [~] Flatpak packaging — builds and runs. A self-hosted manifest (`packaging/flatpak/io.github.ronb1964.TalkType.yml`) and a fully offline Flathub manifest (`packaging/flatpak/flathub/`) both exist, but nothing is published. The Flathub submission (flathub/flathub#9825) was closed and labeled "AI Slop", and no PR carrying that label has ever been merged there, so the realistic routes are a `.flatpak` bundle on GitHub Releases or a self-hosted Flatpak repo.
- [ ] Snap Store packaging
- [ ] PyPI wheel
- [~] Submit to AlternativeTo, Awesome Lists — AlternativeTo is live (2026-03-30). Submitted to awesome-voice-typing (primaprashant/awesome-voice-typing#27, opened 2026-08-27). The maintainer merged #15, #19, #21 and #22 on 2026-09-08 but skipped ours, which had a merge conflict because the "Browse by platform" section was removed. On 2026-09-25 the branch was rebased (now a single table row, mergeable) and a follow-up comment posted. Checked and ruled out: `rcalixte/awesome-wayland` (closed a Linux dictation tool as out of scope), `luong-komorebi/Awesome-Linux-Software` and `natpen/awesome-wayland` (both archived), `sindresorhus/awesome-whisper` (macOS-centric, weak fit).

## Platform Expansion

- [ ] macOS port (pynput, pyautogui, rumps/pystray, PyQt6)
- [ ] Windows port (pynput, pyautogui, pystray, PyInstaller)
- [ ] Platform abstraction layer — `platforms/linux.py`, `platforms/macos.py`, `platforms/windows.py`
- [ ] KDE Plasma helper script (similar to GNOME extension)

## Testing Infrastructure

- [~] Docker containers for cross-DE testing (GNOME, KDE, XFCE) — a `docker-testing/` directory exists; not wired into any routine process.
- [ ] Automated screenshot comparison suite
- [ ] Visual regression testing in CI/CD
- [ ] GTK theme testing across Adwaita, Breeze, Arc-Dark, etc.
- [ ] **Continuous integration** — there is no `.github/workflows/`, so nothing runs the 754 tests (as of 2026-09-17) except by hand. Compounded by the fact that a bare `pytest` *appears* to fail: the venv has no PyGObject, so six test modules error on import. The working invocation is:

  ```
  PYTHONPATH=<repo>/src:/usr/lib64/python3.14/site-packages:/usr/lib/python3.14/site-packages .venv/bin/python -m pytest tests/ -q
  ```

  Worth either recreating the venv with `--system-site-packages` or recording this in `DEV_SETUP.md`.

## Known Limitations (accepted, not bugs to fix)

- **Proper nouns after "undo that"** — continuing a sentence lowercases the first letter, which is right for ordinary words and wrong for names ("Ron" → "ron"). Whisper capitalizes names and sentence starts identically, so the two cannot be told apart. The pronoun "I" and acronyms ("NASA") are special-cased; names are not.
- **Truncation detection without `Content-Length`** — if a server sends no length *and* no checksum is available, a truncated download cannot be detected. All three real callers now supply a checksum, so this is theoretical.
- **`welcome_dialog.py` still calls the blocking `is_model_cached()`** in five places, which loads an entire Whisper model to answer a yes/no question and freezes the dialog. Left alone deliberately: onboarding is a modal flow where the user is already waiting, and changing untested first-run paths is riskier than the freeze. The `tray.py` occurrence — the one that could freeze the *keyboard* — is fixed and pinned by `tests/test_main_loop_blocking.py`.

## Marketing & Promotion

*2026-09 research findings (see the Obsidian note). The problem is visibility, not quality: TalkType's Show HN (2026-04-03) got 2 points, and more than a dozen Linux dictation Show HNs in 2026 got 2–7 points each. Show HN is saturated for this category.*

- [x] **Lead with the Wayland hotkey.** README rewritten 2026-09-26 (commit 9ca7fc1); release notes still to follow the same lead. Make it the first line of the README and the release notes. The competition can't do it reliably:
  - Handy makes Linux users bind a desktop shortcut themselves, and its typing tool (wtype) fails on GNOME.
  - Voxtype says hold-to-talk is impossible on KDE.
  - Murmure dropped Wayland push-to-talk entirely.
  - Suggested pitch: "Hold a key, talk, release. It works on GNOME and KDE Wayland out of the box."
- [ ] **Target KDE, Fedora and Arch users.** Canonical's Myna ships built-in offline dictation in Ubuntu 26.10 (October 2026), covering GNOME/Ubuntu only. It has no voice commands in v1.
- [x] Post in KDE Discuss → Community. Posted 2026-09-26 as Ron_Brand, tagged plasma and wayland; held for moderator approval (first post). Dictee, another offline dictation app, got a good reception there.
- [ ] Post regular "what's new in vX" updates on r/linux, plus r/kde and r/Fedora. **Blocked for now (2026-09-26):** u/ronb1964 has 4 posts, all TalkType, and both r/linux posts (Aug 2025, Feb 2026) plus r/opensource were removed by moderators; r/linux rule 6 caps self-promotion at 10% of posts. Build normal history first, e.g. helpful answers in "Wayland dictation?" threads, before posting again. This is how Vocalinux built its following.
- [~] Reply in the Ubuntu Myna thread (discourse.ubuntu.com/t/84251) and the GNOME "desktop-wide offline speech-to-text" proposal (discourse.gnome.org/t/35858). Myna reply posted 2026-09-26 as ronb1964, awaiting moderator approval. GNOME thread skipped (quiet since June). Both explicitly ask dictation users for input.
- [ ] Pitch Phoronix, Hackaday "Linux Fu", It's FOSS and The Register (Liam Proven).
- [ ] Get into the "best Linux dictation 2026" roundups (blabby.ai, spokenly.app, airtypes.com). TalkType is missing from most of them.
- [ ] Name collision: search results for "TalkType" split with talk-type.com, talktype.app, an iOS app and two other GitHub projects. Consider always writing "TalkType for Linux" in posts.
- [ ] Demo GIF/video creation
- [ ] Reddit launch (r/linux, r/wayland, r/gnome, r/fedora, r/opensource)
- [ ] Hacker News "Show HN" post
- [ ] Product Hunt launch
- [ ] Mastodon/Fosstodon launch
- [ ] Linux blog outreach (OMG! Ubuntu, It's FOSS, Phoronix)
- [ ] YouTube creator outreach (The Linux Experiment, Chris Titus Tech)
- [ ] FOSDEM Accessibility Track presentation

---

*Last updated: 2026-09-26 — hands-free auto-stop shipped in 0.10.0, Dictation Cleanup in 0.9.0. 2026-09-25: added the 2026-09 competitive research items (engines, AI cleanup, marketing). 2026-09-17: Flatpak, Awesome Lists and CI entries refreshed. Every other status was last verified on 2026-08-13 against v0.6.0 and may have drifted since.*

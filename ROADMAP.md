# TalkType Roadmap

Future features, improvements, and expansion ideas. Check off items as they're implemented.

Status markers: `[x]` shipped · `[~]` partly done, see note · `[ ]` not started.

---

## Custom Commands

- [x] Quoted replacement text — if a custom command's replacement is wrapped in quotes (e.g., `"/btw "`), inject it exactly as written, bypassing all normalization (no auto-capitalization, no punctuation changes). Unquoted replacements continue to flow through normalization as today. Implementation: detect quoted values in `_apply_custom_commands()`, protect them with placeholder tokens before `normalize_text()` runs, restore after. Update tooltip on the replacement field in Preferences, the Help dialog, and the README to explain the quoted syntax.
- [ ] Auto-reload custom commands when edited — currently the Preferences Commands tab tells the user "Restart the dictation service for changes to take effect." Should reload `_custom_commands` in app.py automatically (e.g., file-watch on the config or a D-Bus signal from prefs → app) so edits take effect immediately. Removes a friction point users hit every time they touch this list.
- [ ] Importable preset packs of custom commands — a "Linux developer" pack (`why do tool` → `ydotool`, `appy mage` → `AppImage`, `dee bus` → `D-Bus`, etc.), a "Claude Code user" pack with keywords, a "general English" pack with common Whisper trip-ups. Users could install a pack from a "Browse Packs" button in Preferences instead of building their list from scratch. Could grow into a community PR-driven library of shared packs.

## Transcription & AI

- [ ] Silence auto-stop (VAD) with configurable end-of-speech timeout — note: Silero VAD pre-filtering was deliberately **disabled** (`vad_filter=False`) in v0.5.16 because it trimmed speech onsets after pauses. Any auto-stop feature must be built on a separate timer, not by re-enabling that filter.
- [x] Language auto-detect / multilingual models — `language_mode` (auto/manual) in config and Preferences; empty `language` means auto-detect.
- [ ] Language quick switch in tray menu for multilingual users — the setting exists, but only in Preferences. Not in the tray or GNOME menus.
- [ ] Confidence threshold control — filter low-quality transcriptions from background noise
- [ ] Dictation templates — voice-activated templates (e.g., "compose email" inserts email structure)
- [x] Time format normalization — post-process transcribed times like "5 p. m." or "5. 30 p. m." into clean formats like "5 PM" or "5:30 PM". Implemented as `_RE_TIME_FORMAT` / `_fix_time_ampm`. Reordered on 2026-08-03: it used to run *after* capitalization, so "meet at 9 a. m. tomorrow" came out "9 AM Tomorrow".
- [ ] Empty transcription indicator — visual/audio feedback when no speech detected
- [ ] Optional transcription history — last 10-20 transcriptions, click to copy from tray

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

- [x] Periodic auto-check for updates (daily/weekly schedule) — once per day, via `should_check_today()` five seconds after tray launch.

## Security

- [ ] Optional modifier requirement (e.g., Ctrl+F8) to prevent accidental capture — the combo machinery already exists for the Voice Commands hotkey (`_check_modifiers_held`); it just isn't offered for the record hotkeys.

## Distribution & Packaging

- [x] AUR — `talktype-appimage` is published and current. `aur/` holds the packaging sources; `aur-repo/` is the untracked publishing clone (`ssh://aur@aur.archlinux.org/talktype-appimage.git`). Updating a release means bumping `pkgver` and `sha256sums` in both, then committing and pushing `aur-repo`. Note there is no `makepkg` on this machine, so `.SRCINFO` is maintained by hand and must be kept in step with the PKGBUILD.
- [ ] Flatpak packaging
- [ ] Snap Store packaging
- [ ] PyPI wheel
- [ ] RPM spec
- [~] Submit to AlternativeTo, Awesome Lists — AlternativeTo is live (2026-03-30); Awesome Lists not submitted.

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
- [ ] **Continuous integration** — there is no `.github/workflows/`, so nothing runs the 361 tests except by hand. Compounded by the fact that a bare `pytest` *appears* to fail: the venv has no PyGObject, so six test modules error on import. The working invocation is:

  ```
  PYTHONPATH=<repo>/src:/usr/lib64/python3.14/site-packages:/usr/lib/python3.14/site-packages .venv/bin/python -m pytest tests/ -q
  ```

  Worth either recreating the venv with `--system-site-packages` or recording this in `DEV_SETUP.md`.

## Known Limitations (accepted, not bugs to fix)

- **Proper nouns after "undo that"** — continuing a sentence lowercases the first letter, which is right for ordinary words and wrong for names ("Ron" → "ron"). Whisper capitalizes names and sentence starts identically, so the two cannot be told apart. The pronoun "I" and acronyms ("NASA") are special-cased; names are not.
- **Truncation detection without `Content-Length`** — if a server sends no length *and* no checksum is available, a truncated download cannot be detected. All three real callers now supply a checksum, so this is theoretical.
- **`welcome_dialog.py` still calls the blocking `is_model_cached()`** in five places, which loads an entire Whisper model to answer a yes/no question and freezes the dialog. Left alone deliberately: onboarding is a modal flow where the user is already waiting, and changing untested first-run paths is riskier than the freeze. The `tray.py` occurrence — the one that could freeze the *keyboard* — is fixed and pinned by `tests/test_main_loop_blocking.py`.

## Marketing & Promotion

- [ ] Demo GIF/video creation
- [ ] Reddit launch (r/linux, r/wayland, r/gnome, r/fedora, r/opensource)
- [ ] Hacker News "Show HN" post
- [ ] Product Hunt launch
- [ ] Mastodon/Fosstodon launch
- [ ] Linux blog outreach (OMG! Ubuntu, It's FOSS, Phoronix)
- [ ] YouTube creator outreach (The Linux Experiment, Chris Titus Tech)
- [ ] FOSDEM Accessibility Track presentation

---

*Last updated: 2026-08-13 — statuses verified against the source tree as released in v0.6.0.*

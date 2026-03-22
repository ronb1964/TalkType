# TalkType Roadmap

Future features, improvements, and expansion ideas. Check off items as they're implemented.

---

## Transcription & AI

- [ ] Silence auto-stop (VAD) with configurable end-of-speech timeout
- [ ] Language auto-detect / multilingual models
- [ ] Language quick switch in tray menu for multilingual users
- [ ] Confidence threshold control — filter low-quality transcriptions from background noise
- [ ] Dictation templates — voice-activated templates (e.g., "compose email" inserts email structure)
- [ ] Empty transcription indicator — visual/audio feedback when no speech detected
- [ ] Optional transcription history — last 10-20 transcriptions, click to copy from tray

## Audio

- [ ] Different beep sounds — selectable audio feedback styles
- [ ] Beep volume control
- [ ] Custom sound files for start/stop feedback
- [ ] Background noise detection — warn if environment is too noisy
- [ ] Automatic mic selection — switch to best available mic
- [ ] Multi-microphone quick switcher in tray menu
- [ ] Live audio level indicator in GNOME panel

## UI Improvements

- [ ] Session statistics — words transcribed, recording time, characters typed, average WPM
- [ ] Waveform visualization during recording
- [ ] Custom symbolic icon for TalkType branding (mic with "T" badge or speech bubble)
- [ ] Native Wayland positioning via gtk-layer-shell
- [ ] Keyboard shortcuts reference dialog from tray menu
- [ ] Voice commands quick access with test feature
- [ ] Glassmorphism dialog effects — frosted glass blur backgrounds
- [ ] Animated state transitions and loading indicators

## Per-App & Context Features

- [ ] Per-app dictation profiles — different hotkeys/models per application
- [ ] Auto-disable in password fields and sensitive inputs
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
- [ ] Check for Updates in GNOME extension menu via D-Bus
- [ ] Activities search integration
- [ ] Publish extension to extensions.gnome.org

## Settings Management

- [ ] Backup settings — export config, custom commands, and preferences to a file
- [ ] Restore settings — import a previously saved backup to restore your setup
- [ ] Settings accessible from Preferences (Backup / Restore buttons)

## First-Run & Onboarding

- [ ] Guided `/dev/uinput` permission setup with pkexec one-click fix
- [ ] Automated end-to-end typing test on first run to verify text injection works
- [ ] Graceful clipboard fallback — "copy to clipboard, press Ctrl+V" when ydotool unavailable

## Update System

- [ ] Periodic auto-check for updates (daily/weekly schedule)

## Security

- [ ] Optional modifier requirement (e.g., Ctrl+F8) to prevent accidental capture

## Distribution & Packaging

- [ ] Flatpak packaging
- [ ] Snap Store packaging
- [ ] PyPI wheel
- [ ] RPM spec
- [ ] Submit to AlternativeTo, Awesome Lists

## Platform Expansion

- [ ] macOS port (pynput, pyautogui, rumps/pystray, PyQt6)
- [ ] Windows port (pynput, pyautogui, pystray, PyInstaller)
- [ ] Platform abstraction layer — `platforms/linux.py`, `platforms/macos.py`, `platforms/windows.py`
- [ ] KDE Plasma helper script (similar to GNOME extension)

## Testing Infrastructure

- [ ] Docker containers for cross-DE testing (GNOME, KDE, XFCE)
- [ ] Automated screenshot comparison suite
- [ ] Visual regression testing in CI/CD
- [ ] GTK theme testing across Adwaita, Breeze, Arc-Dark, etc.

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

*Last updated: 2026-03-22 (v0.5.15)*

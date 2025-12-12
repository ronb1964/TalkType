# TalkType – Developer Notes

> **Purpose:** Voice dictation tool for Linux (Wayland) using Faster-Whisper, `ydotool`, and hotkey press-and-hold to inject text into the active window.
> Includes punctuation and formatting normalization, optional tray icon, and systemd integration.

---

## ⚠️ IMPORTANT: Read CLAUDE_RULES.md First!

**Before working on this project, AI assistants MUST read [CLAUDE_RULES.md](./CLAUDE_RULES.md).**

This file contains critical non-negotiable rules including:
- NEVER break the dev environment (user relies on it daily!)
- AppImage builds MUST be completely isolated from dev environment
- Build in clean Ubuntu 22.04 containers ONLY
- Bundle ALL dependencies - never copy from host system
- Cross-platform compatibility requirements

**Failure to follow these rules wastes time and breaks the user's workflow.**

---

## 📌 Table of Contents
1. [Project Overview](#project-overview)
2. [AppImage Cross-Compatibility Requirements](#appimage-cross-compatibility-requirements)
3. [Architecture](#architecture)
4. [Hotkey Behavior](#hotkey-behavior)
5. [Normalizer Rules](#normalizer-rules)
6. [Systemd Services](#systemd-services)
7. [Tray App](#tray-app)
8. [Testing](#testing)
9. [Git & Repo Setup](#git--repo-setup)
10. [Known Issues](#known-issues)
11. [Future Ideas](#future-ideas)

---

## Project Overview
- **Name:** TalkType
- **Goal:**  
  - Press and hold **F8** → Start listening.  
  - Release **F8** → Stop listening, normalize text, insert into active window.
  - Press **Esc** while holding → Cancel.
- Built with **Poetry**, Python 3.12.
- Works on **Wayland** via `ydotool`.

---

## AppImage Cross-Compatibility Requirements

**⚠️ CRITICAL: This project is distributed as an AppImage and must work across many Linux distributions and desktop environments.**

### Audio Backend Support
Always support multiple audio backends with graceful fallbacks:

1. **PipeWire** (modern Fedora, Nobara, newer Ubuntu)
   - Command: `wpctl`
   - Example: `wpctl get-volume @DEFAULT_AUDIO_SOURCE@`

2. **PulseAudio** (older/traditional systems)
   - Command: `pactl`
   - Example: `pactl get-source-volume @DEFAULT_SOURCE@`

3. **ALSA-only** (minimal systems)
   - No standardized volume control - graceful degradation required

### Implementation Pattern
```python
def set_system_volume(volume):
    # Try PipeWire first (most modern systems)
    try:
        subprocess.run(['wpctl', 'set-volume', '@DEFAULT_AUDIO_SOURCE@', f'{volume}%'], ...)
        return
    except FileNotFoundError:
        pass

    # Fall back to PulseAudio
    try:
        subprocess.run(['pactl', 'set-source-volume', '@DEFAULT_SOURCE@', f'{volume}%'], ...)
        return
    except FileNotFoundError:
        pass

    # Neither available - inform user gracefully
    logger.warning("Volume control not available (neither wpctl nor pactl found)")
```

### General Guidelines
- **Never assume** a specific desktop environment (GNOME, KDE, XFCE, etc.)
- **Never assume** specific system commands exist
- **Always provide fallbacks** when system features aren't available
- **Test on multiple distros** when possible (Fedora, Ubuntu, Arch, etc.)
- **Graceful degradation** - features should fail gracefully, not crash

### Desktop Environment Variations
- Some systems use GNOME, others KDE, XFCE, etc.
- Tray icon implementations vary (StatusNotifier vs legacy)
- System dialogs and notifications differ
- Audio routing and device naming varies

### When Making Changes
Before implementing features that interact with the system:
1. Consider: "Will this work on Ubuntu AND Fedora AND Arch?"
2. Check: "What if this system command doesn't exist?"
3. Implement: Multiple detection methods with fallbacks
4. Document: Which systems/scenarios are supported

---

## Architecture

### Main Components
| File | Purpose |
|------|---------|
| `src/ron_dictation/app.py` | Main listener loop, integrates Faster-Whisper + hotkey capture + ydotool typing. |
| `src/ron_dictation/normalize.py` | Text cleanup rules (punctuation, spacing, capitalization, tabs). |
| `src/ron_dictation/config.py` | User-configurable settings (hotkeys, beeps, model path). |
| `src/ron_dictation/tray.py` | Optional tray icon for status & quick settings. |

### Dependencies
- `faster-whisper` (speech-to-text)
- `evdev` (keyboard events)
- `sounddevice` (audio capture)
- `ydotool` (text injection on Wayland)
- `pystray` (tray icon)
- `Pillow` (icons for tray)
- `pytest` (testing normalizer)

---

## Hotkey Behavior
- **F8 Press:**  
  - Start recording, play "start beep".
- **F8 Release:**  
  - Stop recording, normalize text, inject via `ydotool`.
- **Esc While Holding:**  
  - Cancels current dictation, plays "cancel beep".
- **Spacing Fix:**  
  - If last char in existing text is `.` (period), insert space before continuing new sentence.

---

## Normalizer Rules

**Core behaviors:**
- Capitalize first word of sentences.
- Replace:
  - `"dot dot dot"` → `…`
  - `"comma"` → `,`
  - `"exclamation point"` → `!`
  - `"open quote"` / `"close quote"` → smart quotes `“”`
- Collapse extra spaces.
- Preserve **leading tabs** after newline, strip only spaces after tabs.
- Ensure space after punctuation where appropriate.
- Auto-capitalize after `.`, `?`, `!`, and `…`.

**Key fix:**  
```python
# Preserve leading tabs but strip spaces after them
lines = []
for raw_line in text.split("\n"):
    m = re.match(r"^(\t+)(.*)$", raw_line)
    if m:
        tabs, rest = m.groups()
        rest = rest.lstrip(" ")
        lines.append(tabs + rest)
    else:
        lines.append(raw_line)
text = "\n".join(lines)
Systemd Services
Active Service (ron-dictation.service)
ini
Copy
Edit
[Unit]
Description=Ron Dictation Listener (F8) - Faster-Whisper + ydotool
After=ydotool.service

[Service]
ExecStart=/home/ron/.cache/pypoetry/virtualenvs/ron-dictation-PjtP02uz-py3.12/bin/python -m ron_dictation.app
Restart=always
RestartSec=1

[Install]
WantedBy=default.target
Commands:

bash
Copy
Edit
systemctl --user daemon-reload
systemctl --user enable --now ron-dictation.service
systemctl --user status ron-dictation.service
Old service cleanup:

bash
Copy
Edit
systemctl --user stop voice-dictation.service
systemctl --user disable voice-dictation.service
systemctl --user mask voice-dictation.service
rm -f ~/.config/systemd/user/voice-dictation.service
systemctl --user daemon-reload
Tray App
Command:

bash
Copy
Edit
poetry run dictate-tray &
Known:

On Wayland, some desktops don’t display tray icons without a StatusNotifier/legacy tray extension.

Possible fix: Install gnome-shell-extension-appindicator.

Testing
Run tests:

bash
Copy
Edit
poetry run pytest -q
All should pass:

Copy
Edit
5 passed in 0.03s
Git & Repo Setup
Remote:

scss
Copy
Edit
git@github.com:ronb1964/TalkType.git
Setup SSH:

bash
Copy
Edit
ssh-keygen -t ed25519 -C "ronb1964@gmail.com"
ssh-add ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub  # Add to GitHub SSH keys
ssh -T git@github.com
Push sequence:

bash
Copy
Edit
git fetch origin main
git rebase origin/main
git push -u origin main
Known Issues
Tray icon may not show without desktop support.

Cursor insertion after period now fixed to add space; still needs monitoring for other punctuation.

GUI settings window planned — not yet implemented.

Future Ideas
GUI settings window for hotkeys, punctuation preferences, audio device.

Per-app dictation profiles.

Language model switching from tray menu.

Optional transcription history.

Temporary "pause dictation" mode via tray.

pgsql
Copy
Edit

---

If you save this as `README_DEV.md` in your project root, Cursor will use it as context whenever you’re chatting about the repo.  
That means you’ll be able to say things like *“Let’s tweak the normalizer to handle semicolons differently”* and Cursor will already know the current setup.

Do you want me to also **add a quick “setup-from-scratch” section** to this so you can get the project running on a fresh machine in minutes? That might be handy for future reinstalls.








Ask ChatGPT


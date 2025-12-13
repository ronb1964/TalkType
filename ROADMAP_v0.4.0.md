# TalkType Roadmap

Last updated: December 12, 2025

All features are designed to add value **without increasing AppImage size**.

---

## Recently Completed

### Custom Voice Commands
- User-definable phrase replacements via `~/.config/talktype/custom_commands.toml`
- Full Preferences UI with Custom Commands tab (add/edit/delete)
- Case-insensitive matching with word boundaries

### Smart Injection Mode (Auto/Paste/Type)
- Fast process-based detection (0.024s vs 15+ seconds with AT-SPI)
- Defaults to paste mode (works universally)
- Universal Ctrl+Shift+V paste (works in terminals AND regular apps)

### "New Paragraph" Voice Command
- Say "new paragraph" for double newline

### Performance Optimization
- Text injection reduced from 16.67s to 0.93s (18x faster)
- Removed slow AT-SPI detection that caused 15+ second delays

### Recording Indicator
- Visual feedback during recording
- Configurable position and size

---

## Phase 1: v0.4.0 (Current)

### Voice-Activated Undo Commands
**Status:** Not started
**Priority:** High

Voice commands to delete portions of recent dictation:
- **"undo last word"** - Delete the last word typed
- **"undo last sentence"** - Delete back to last period/question/exclamation
- **"undo last paragraph"** - Delete back to last paragraph break

**Implementation:**
- Track last inserted text with word/sentence/paragraph boundaries
- Calculate backspaces needed
- Send backspace keypresses via ydotool

---

### Fix GTK Deprecation Warning
**Status:** Not started
**Priority:** Low (cosmetic)

```
DeprecationWarning: Gtk.Dialog.get_action_area is deprecated
```

Replace deprecated `get_action_area()` with modern GTK3 patterns.

---

### Performance Mode Presets
**Status:** Not started
**Priority:** Medium

Quick presets in tray menu:
- **Fastest** - tiny model, CPU
- **Balanced** - small model, GPU if available
- **Most Accurate** - large-v3, GPU
- **Battery Saver** - tiny, CPU, auto-timeout

One-click optimization for different scenarios.

---

## Phase 2: v0.5.0 (Enhanced UX)

### Session Statistics
Track and display in tray menu:
- Words transcribed
- Recording time
- Characters typed
- Average WPM

### Transcription History
- Keep last 10-20 transcriptions in memory
- Click to copy to clipboard
- Accessible from tray menu

### Empty Transcription Indicator
- Visual/audio feedback when no speech detected

---

## Phase 3: v0.6.0 (Power Features)

### Language Quick Switch
Tray menu language toggle for multilingual users.

### Audio Feedback Options
- Different beep sounds
- Volume control
- Custom sound files

### Dictation Templates
Voice-activated templates (e.g., "compose email" inserts email template).

### Confidence Threshold Control
Filter low-quality transcriptions from background noise.

---

## Future / Nice to Have

### Native Wayland Positioning (gtk-layer-shell)
Currently using XWayland fallback for window positioning.

### Multi-Microphone Support
Quick mic switcher in tray menu.

### Keyboard Shortcuts Reference
Quick reference dialog from tray menu.

### Voice Commands Quick Access
Direct tray menu access to voice commands reference with test feature.

---

## Explicitly Avoid (Would Increase Size)

- Additional bundled AI models (keep download-on-demand)
- Built-in text editor
- Cloud sync features
- Heavy Python dependencies
- Bundled documentation

---

## Development Guidelines

### Keep AppImage Size Small
- No new binary dependencies
- Minimize new Python packages
- Use built-in libraries when possible

### User Experience Focus
- Features should be discoverable
- No breaking changes to existing configs
- Clear error messages

---

## Notes

**Current AppImage size:** ~870MB (target: under 1GB)

**AT-SPI Note:** AT-SPI accessibility framework was found to cause 15+ second delays when the D-Bus socket is unavailable (common on Wayland). The current implementation uses fast process-based detection instead, falling back to paste mode which works universally with Ctrl+Shift+V.

# TalkType v0.4.0 Roadmap

## Feature Ideas for Next Version

All features below are designed to add value **without increasing AppImage size**.

---

## 🎯 High Priority (High Value, Easy to Implement)

### 1. Quick Model Switcher in Tray Menu
**Current:** Must open Preferences to change model
**Proposed:** Add model selection directly in tray menu

```
System Tray →
  Start/Stop Service
  Model: large-v3 ▼
    ├── tiny (fastest)
    ├── base
    ├── small
    ├── medium
    └── large-v3 ✓
  Preferences...
```

**Implementation:**
- Add submenu to tray menu
- Update config on selection
- Reload model if service is running
- Show current model with checkmark

**Benefit:** Quick model switching for different use cases (speed vs accuracy)

---

### 2. Custom Voice Commands
**Current:** Fixed set of voice commands (comma, period, new line, etc.)
**Proposed:** User-definable phrase replacements

**Example Use Cases:**
- "my email" → "yourname@example.com"
- "my address" → "123 Main St, City, State"
- "signature" → "Best regards,\nRon"
- "company name" → "TalkType Technologies Inc."
- "phone number" → "(555) 123-4567"

**Implementation:**
- New section in Preferences: "Custom Commands"
- Simple table: Phrase → Replacement
- Store in config.toml as dict
- Process before smart punctuation

**File:** `~/.config/talktype/custom_commands.toml`
```toml
[custom_commands]
"my email" = "ron@example.com"
"my address" = "123 Main St, Springfield"
"signature" = "Best regards,\nRon"
```

**Benefit:** Massive time savings for frequently used text

---

### 3. Voice-Activated Undo Commands
**Current:** No way to undo transcribed text
**Proposed:** Voice commands to delete portions of recent dictation

**Voice Commands:**
- **"undo last word"** - Delete the last word typed
- **"undo last sentence"** - Delete the last sentence (up to previous period/question mark/exclamation)
- **"undo last paragraph"** - Delete everything since last paragraph break

**Implementation:**
- Track last inserted text with word/sentence/paragraph boundaries
- Detect specific multi-word undo phrases (won't trigger on just "undo" alone)
- Calculate backspaces needed based on boundary markers
- Send backspace keypresses to delete specified portion
- Similar to existing voice commands (new line, comma, etc.)

**Why voice-activated instead of hotkey:**
- Keeps hands-free workflow intact
- Natural for a dictation app
- No need to remember keyboard shortcuts

**Safety:**
- Phrases like "I need to undo that" won't trigger (only exact multi-word commands)
- Avoids false positives like "scratch that itch"

**Benefit:** Quick, hands-free correction without breaking dictation flow

---

### 4. Fix GTK Deprecation Warning
**Current Issue:**
```
DeprecationWarning: Gtk.Dialog.get_action_area is deprecated
```

**Fix:** Replace deprecated method calls in:
- `src/talktype/app.py:95`
- Any other instances

**Implementation:**
```python
# Old (deprecated)
button_box = dialog.get_action_area()

# New (correct)
content_area = dialog.get_content_area()
# Create button box manually
```

**Benefit:** Future GTK compatibility

---

---

## 📊 Medium Priority

### 6. Session Statistics
**Track and display:**
- Words transcribed (today/this session)
- Total recording time
- Characters typed
- Average transcription speed (words/minute)

**Implementation:**
- Add counter variables to app.py
- Display in tray menu or preferences "About" tab
- Reset on service start/stop
- Optional: Save daily stats to file

**UI Location:** Tray menu → "Statistics..."
```
Session Statistics
─────────────────
Words transcribed: 1,247
Recording time: 15m 32s
Avg speed: 42 wpm
Characters typed: 8,234
```

---

### 7. Transcription History
**Keep last 10-20 transcriptions in memory**

**Implementation:**
- Circular buffer in memory (not persisted)
- Accessible from tray menu → "Recent Transcriptions"
- Each entry: timestamp + text
- Click to copy to clipboard

**UI:**
```
Recent Transcriptions →
  [14:32] This is a test of the download...
  [14:30] Everything seems to be working.
  [14:28] I do have a question though...
  ...
  Clear History
```

**Benefit:** Review/recover recent dictations

---

### 8. Performance Mode Presets
**Quick configuration presets**

**Presets:**
- **Fastest** - tiny model, CPU, minimal latency
- **Balanced** - small model, GPU (if available)
- **Most Accurate** - large-v3, GPU, best quality
- **Battery Saver** - Auto-timeout enabled, CPU mode

**Implementation:**
- Add "Performance Mode" submenu in tray
- Each preset updates multiple config values
- Show current mode

**Benefit:** One-click optimization for different scenarios

---

### 9. Language Quick Switch
**If multiple languages supported:**

Add language toggle in tray menu instead of requiring preferences window.

```
Language ▼
  ├── English ✓
  ├── Spanish
  ├── French
  └── German
```

**Benefit:** Quick language switching for multilingual users

---

### 10. Recording Status Overlay/Pop-up
**Current:** No visual feedback while recording (only audio beep and tray icon)
**Proposed:** On-screen indicator showing active recording

**Visual Options:**
- **Small floating window** - Semi-transparent, shows "🎙️ Recording..." with animated waveform or pulse
- **Toast notification style** - Appears in corner, auto-positions away from cursor
- **Minimal overlay** - Just a red dot or mic icon that follows cursor
- **Status bar widget** - Small bar at top/bottom of screen

**Features:**
- Animated to show it's active (pulsing, waveform, spinning)
- Shows elapsed recording time
- Click to cancel recording
- Configurable position (top-left/right, bottom-left/right, follow cursor)
- Configurable opacity/size
- Option to disable if user prefers audio-only feedback

**Implementation:**
- Use GTK window with `set_keep_above(True)` for always-on-top
- Semi-transparent background (`set_opacity()`)
- Position near cursor or in corner based on config
- Simple animation (GLib.timeout_add for updates)
- Minimal CPU usage
- Show on recording start, hide on recording stop

**UI Mock:**
```
┌─────────────────┐
│ 🎙️ Recording... │
│    0:03         │
└─────────────────┘
```

**Config Options:**
```toml
[recording_indicator]
enabled = true
style = "floating"  # floating, toast, minimal, bar
position = "top-right"  # or follow_cursor
opacity = 0.9
show_timer = true
```

**Benefit:** Clear visual feedback that recording is active, especially helpful when audio beeps are disabled

---

### 11. Empty Transcription Visual Indicator
**Current:** Console shows `(No speech recognized)`
**Proposed:** Brief visual feedback

**Options:**
- Desktop notification: "No speech detected"
- Status bar message
- Different beep sound

**Implementation:**
- Detect empty/whitespace-only transcription
- Show notification if enabled in config
- Optional: Different audio feedback

---

## 💡 Nice to Have (Lower Priority)

### 11. Audio Feedback Options
**More beep sound choices:**
- Different styles (chirp, click, tone, voice)
- Volume control for beeps
- Custom sound files

**Implementation:**
- Add sound file selector in preferences
- Bundle a few default sounds (tiny size)
- Allow custom .wav files

---

### 12. Dictation Templates
**Voice-activated templates:**

**Examples:**
- "compose email" → Inserts email template
- "meeting notes" → Adds date/time header
- "code comment" → Programming comment format

**Implementation:**
- Predefined templates in config
- Triggered by specific phrases
- Variables: {date}, {time}, {cursor}

**Template Example:**
```toml
[templates.email]
trigger = "compose email"
content = """
Dear {cursor},

Best regards,
Ron
"""
```

---

### 13. Confidence Threshold Control
**Filter low-quality transcriptions**

**Implementation:**
- Add slider in Preferences: "Minimum Confidence"
- Reject transcriptions below threshold
- Show notification when rejected

**Benefit:** Reduce incorrect transcriptions from background noise

---

### 14. Keyboard Shortcuts Reference
**Quick reference dialog:**

Tray menu → "Keyboard Shortcuts" → Shows dialog with all hotkeys

```
Keyboard Shortcuts
──────────────────
F8          Start/Stop Recording (Hold Mode)
F9          Toggle Recording (Toggle Mode)
Ctrl+Shift+Z  Undo Last Dictation
Esc         Cancel Recording

Voice Commands
──────────────
"comma"     Insert comma
"period"    Insert period
"new line"  Line break
...
```

---

### 15. Multi-Microphone Support
**Current:** Uses default microphone
**Proposed:** Quick microphone switcher

**Implementation:**
- List available audio devices
- Add submenu in tray to select microphone
- Remember selection in config

---

## 🚫 Explicitly Avoid (Would Increase Size)

These features would bloat the AppImage:
- ❌ Additional AI models (keep download-on-demand)
- ❌ Built-in text editor
- ❌ Cloud sync features
- ❌ More Python dependencies
- ❌ Bundled documentation (keep online/README)

---

## Implementation Priority

### Phase 1: v0.4.0 (Quick Wins)
**Target: 1-2 weeks**

1. Fix GTK deprecation warning
2. Quick Model Switcher (tray menu)
3. Voice-activated undo commands (undo last word/sentence/paragraph)
4. Custom voice commands (basic user-defined phrases)

### Phase 2: v0.5.0 (Enhanced UX)
**Target: 2-3 weeks**

6. Session statistics
7. Transcription history
8. Performance mode presets
9. Empty transcription visual indicator

### Phase 3: v0.6.0 (Power Features)
**Target: 3-4 weeks**

10. Language quick switch
11. Audio feedback options
12. Dictation templates
13. Confidence threshold control

### Phase 4: Future (Nice to Have)
14. Keyboard shortcuts reference
15. Multi-microphone support

---

## Development Guidelines for v0.4.0+

### Keep AppImage Size Small
- No new binary dependencies
- Minimize new Python packages
- Use built-in libraries when possible
- Keep features configuration-based

### Maintain Code Quality
- Add tests for new features
- Update documentation
- Keep backwards compatibility
- Follow existing code style

### User Experience Focus
- Features should be discoverable
- No breaking changes to existing configs
- Smooth upgrade path
- Clear error messages

---

## Testing Checklist for New Features

Before release:
- [ ] Test on fresh install (first-run experience)
- [ ] Test with existing config (upgrade path)
- [ ] Test all new features
- [ ] Verify AppImage size unchanged or smaller
- [ ] Update README.md
- [ ] Update AppStream metadata
- [ ] Add to CHANGELOG

---

## Future Versions Beyond v0.6.0

### Possible Major Features (Separate Discussion)
- Cross-platform support (macOS/Windows) - See CROSS_PLATFORM_PORTING_GUIDE.md
- Plugin system for custom processing
- Integration with text editors (VS Code, etc.)
- Accessibility improvements
- Voice training/customization

---

## Notes from Development Session (2025-10-09)

**User Feedback:**
- "I like pretty much all of them" - All suggested features approved
- Focus on features that don't increase file size
- Current AppImage size: 870MB (keep under 1GB)
- Testing confirmed v0.3.6 works perfectly

**Successful v0.3.6 Test:**
- ✅ CUDA detection working
- ✅ First-run experience smooth
- ✅ Hotkey verification working
- ✅ Voice commands functional ("new line")
- ✅ Text injection working
- ✅ Model loading successful (large-v3)

**Next Session:**
Start implementing Phase 1 features for v0.4.0

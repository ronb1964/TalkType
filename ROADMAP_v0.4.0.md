# TalkType v0.4.0 Roadmap

## Feature Ideas for Next Version

All features below are designed to add value **without increasing AppImage size**.

---

## 🎯 High Priority (High Value, Easy to Implement)

### Smart Injection Mode Detection (AT-SPI)
**Current:** User manually chooses between clipboard paste or keyboard typing
**Problem:** Clipboard paste doesn't work in URL bars, password fields, and other special inputs
**Proposed:** Automatically detect the best injection method based on focused widget

**Detection Logic:**
```
Use AT-SPI to detect focused widget type:

If terminal emulator:
    → Use Ctrl+Shift+V (already implemented)
If URL/address bar:
    → Use keyboard typing (Ctrl+V doesn't work)
If password field:
    → Use keyboard typing (more reliable)
If standard text field:
    → Use clipboard paste (fastest for long text)
Fallback:
    → Try AT-SPI direct text insertion if supported
```

**AT-SPI Widget Roles to Detect:**
- `ATK_ROLE_TERMINAL` → Terminal
- `ATK_ROLE_PASSWORD_TEXT` → Password field
- `ATK_ROLE_ENTRY` with URI context → URL bar
- `ATK_ROLE_TEXT` / `ATK_ROLE_ENTRY` → Normal text field

**Implementation:**
1. Extend existing `atspi_helper.py` to detect widget roles
2. Add role-based injection method selection in `app.py`
3. User preference becomes "Auto" (smart), "Paste", or "Type"
4. Log which method was chosen and why (for debugging)

**Benefits:**
- User just dictates - app figures out the best method
- Fast paste where it works, reliable typing where it doesn't
- Handles edge cases automatically
- Future-proof: add new rules as we discover quirks

**Ultimate Goal:**
Use AT-SPI **direct text insertion** where supported - bypasses both paste and typing entirely, works in any AT-SPI-enabled widget.

---

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

### Native Wayland Window Positioning (gtk-layer-shell)
**Current:** Recording indicator positioning uses XWayland fallback (`GDK_BACKEND=x11`)
**Problem:** Native Wayland doesn't allow apps to position their own windows
**Proposed:** Use `gtk-layer-shell` library for proper Wayland positioning

**Current Workaround:**
- Force XWayland via `GDK_BACKEND=x11` in run scripts
- Works but uses compatibility layer instead of native Wayland

**Proper Implementation:**
1. Add smart display detection:
   ```
   If Wayland AND gtk-layer-shell available:
       → Use native Wayland with layer-shell positioning
   Else if Wayland (no layer-shell):
       → Fall back to XWayland OR accept center-only positioning
   Else (X11):
       → Use X11 normally (positioning works natively)
   ```

2. Update `recording_indicator.py` to use:
   ```python
   gi.require_version('GtkLayerShell', '0.1')
   from gi.repository import GtkLayerShell
   
   GtkLayerShell.init_for_window(window)
   GtkLayerShell.set_layer(window, GtkLayerShell.Layer.OVERLAY)
   GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.TOP, True)  # etc.
   ```

**Dependencies:**
- `gtk-layer-shell` package (available in most distros: Fedora, Ubuntu, Arch)
- Fedora/Nobara: `sudo dnf install gtk-layer-shell`
- Ubuntu/Debian: `sudo apt install libgtk-layer-shell-dev gir1.2-gtklayershell-0.1`

**Benefits:**
- Native Wayland performance (no XWayland overhead)
- Proper HiDPI scaling
- Future-proof as X11 gets deprecated
- Works on pure Wayland systems (no XWayland installed)

**Fallback Strategy:**
- If gtk-layer-shell not installed, gracefully fall back to XWayland or center-only
- Show note in Preferences that positioning requires gtk-layer-shell on Wayland

---

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

### 14. Voice Commands Quick Access & Cheat Sheet
**Current:** Voice commands reference buried in Help → Voice Commands tab
**Proposed:** Direct access from tray menu with enhanced features

**Features:**
1. **Tray Menu Quick Access**
   - Add "Voice Commands" directly to tray menu
   - Opens a focused dialog showing all available commands
   - No need to navigate through Help

2. **Printable Cheat Sheet**
   - "Print / Export" button in the dialog
   - Generates a clean, printer-friendly PDF or HTML
   - Users can print and keep near their desk
   - Compact format: 1-page reference card

3. **Test Commands Feature**
   - "Test" button next to each command category
   - Opens a test area where user can try commands
   - Shows live preview: what you said → what gets inserted
   - Helps users learn and verify commands work

**UI Mock:**
```
┌─────────────────────────────────────────┐
│ 🗣️ Voice Commands Reference            │
├─────────────────────────────────────────┤
│ Punctuation:                            │
│   "comma" → ,    "period" → .           │
│   "question mark" → ?                   │
│                          [Test These]   │
├─────────────────────────────────────────┤
│ Formatting:                             │
│   "new line" → ↵    "new paragraph" → ¶ │
│   "tab" → ⇥                             │
│                          [Test These]   │
├─────────────────────────────────────────┤
│ [🖨️ Print Cheat Sheet]  [Close]        │
└─────────────────────────────────────────┘
```

**Implementation:**
- Add "Voice Commands" menu item to tray.py
- Create new `voice_commands_dialog.py` with:
  - Tabular display of all commands
  - Test area with live preview
  - Print/export functionality (use GTK print API or generate HTML)

**Benefit:** Users discover and learn commands easily, improving their dictation workflow

---

### 15. Keyboard Shortcuts Reference
**Quick reference dialog:**

Tray menu → "Keyboard Shortcuts" → Shows dialog with all hotkeys

```
Keyboard Shortcuts
──────────────────
F8          Start/Stop Recording (Hold Mode)
F9          Toggle Recording (Toggle Mode)
Ctrl+Shift+Z  Undo Last Dictation
Esc         Cancel Recording
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

## 🔬 Research & Exploration

### AT-SPI Integration (Assistive Technology Service Provider Interface)
**Status:** Research/Prototype Phase
**Added:** 2025-10-18
**Priority:** High potential impact, needs investigation

**What is AT-SPI?**
AT-SPI is the Linux accessibility framework used by GNOME, KDE, and other desktop environments. It provides programmatic access to UI elements and text content in applications.

**Potential Benefits for TalkType:**

1. **Smart Text Operations**
   - Detect and replace selected text
   - Know exact cursor position in any application
   - Get context around cursor (current paragraph, sentence)
   - Know if text is selected (and what text)

2. **Intelligent Text Insertion**
   - Insert text directly into application's text buffer (more reliable than ydotool)
   - Context-aware dictation (know if in password field, code editor, document, etc.)
   - Better handling of special characters and keyboard layouts
   - Potential integration with application undo buffers

3. **Advanced Features**
   - "What did I just say?" - Read back recent dictation
   - Navigate by sentence/paragraph with voice commands
   - Context-aware auto-capitalization (e.g., don't capitalize in code editors)
   - Detect document structure (headings, lists, paragraphs)

**Example Workflow:**
```
Current (ydotool):
1. Press F8
2. Speak: "Hello world period"
3. TalkType types: "Hello world."

With AT-SPI:
1. Press F8
2. TalkType queries: Where's cursor? Is text selected? What app?
3. Speak: "Hello world period"
4. If text selected → replace with "Hello world."
5. If in middle of sentence → insert intelligently
6. If in code editor → adjust capitalization/formatting
```

**Implementation Approach:**
- **Hybrid approach:** Use AT-SPI where available, fall back to ydotool
- Start with basic features:
  - Get caret position
  - Detect selected text
  - Insert text via AT-SPI
- Add advanced features later:
  - Context reading
  - Smart text replacement
  - Application-specific behaviors

**Dependencies:**
- `python3-pyatspi` (available in most distros)
- May need to bundle in AppImage

**Challenges:**
- Not all applications support AT-SPI properly
- More complex than ydotool keyboard simulation
- Need robust fallback for unsupported apps
- Testing across different apps and environments

**Next Steps:**
1. Create prototype script to test AT-SPI capabilities
2. Test with common applications (Firefox, gedit, VS Code, terminals, etc.)
3. Measure reliability vs ydotool
4. Decide on integration strategy (replace, supplement, or optional)
5. Document which apps work well with AT-SPI vs need ydotool

**User Request:**
> "What can incorporating this do for us?"

Answer: The biggest wins would be:
- **Replace selected text** - Select text, dictate replacement (huge workflow improvement)
- **Know context** - TalkType could show current app/context in tray
- **More reliable** - Especially in GTK apps (gedit, GNOME apps, etc.)
- **Smarter behavior** - Auto-adjust based on application type

**Resources:**
- [AT-SPI Documentation](https://www.freedesktop.org/wiki/Accessibility/AT-SPI2/)
- Python pyatspi examples
- Accessibility testing tools

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

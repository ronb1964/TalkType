# Welcome Dialog Design Specification

**Critical: This structure MUST be maintained exactly across all scenarios**

## CRITICAL: Cross-Desktop Compatibility

**TalkType is distributed as an AppImage for use across ALL Linux desktop environments:**
- Must work on GNOME, KDE Plasma, XFCE, Cinnamon, MATE, etc.
- Must work on both X11 and Wayland
- NEVER use desktop-specific APIs or features (except when explicitly detecting GNOME for optional extension)
- Use only standard GTK3 widgets and functions
- Test assumptions about screen APIs - they may behave differently across DEs
- Avoid deprecated GTK/GDK functions that may not work consistently

## Core Design Principle

**ALL scenarios share the SAME base structure.** The ONLY thing that changes is whether the "Optional Features" section appears.

---

## Universal Base Structure (ALWAYS SHOWN)

This exact structure appears in **every** welcome dialog, regardless of hardware/desktop:

### 1. Header Section
```
🎙️ Welcome to TalkType!
AI-powered speech recognition for Linux
[horizontal separator]
```

### 2. Main Description
```
Privacy-focused, AI-powered dictation that runs entirely on your computer.
```
**IMPORTANT**: This line must NOT wrap - display as single line (`set_line_wrap(False)`)

### 3. Key Features Section
```
✨ Key Features

  🎤 Press-and-hold dictation (default: F8 key)
  🗣️ Voice commands: "period", "comma", "new paragraph"
  🤖 Powered by OpenAI's Whisper AI
  🔒 100% local - your voice never leaves your computer
  ⚙️ Configurable hotkeys and preferences

[horizontal separator]
```

### 4. Quick Start Section
```
💡 Quick Start

  • Press your hotkey to start dictating
  • Access settings from the system tray icon
  • Click "Help" in the menu for documentation
```

### 5. Bottom Section (ALWAYS SHOWN)
```
[spacer]

Next: You'll test your hotkeys to ensure they work correctly

[Centered "Let's Go!" button - 200x40px]
```

---

## Optional Features Section (CONDITIONAL)

This section appears ONLY when CUDA/GNOME are detected. It is inserted AFTER "Quick Start" and BEFORE "Next:".

```
[horizontal separator]

⚙️ Optional Features

[One or both of the following, depending on detection:]

  ☐ Install GNOME Extension (~3KB)
      🎨 Panel indicator with quick controls and service management
      (Requires logging out and back in after installation)

  ☐ Download CUDA Libraries (~800MB)
      🚀 3-5x faster transcription with NVIDIA GPU
      (Details about CUDA benefits)
```

---

## All Four Scenarios

### Scenario 1: No NVIDIA, No GNOME
- Shows: Base structure only
- Window: 580x700px
- Button: "Let's Go!" (centered, 200x40px)
- Test file: `test_welcome_scenario1.py`
- **Behavior:** Opens full size, no scrolling on screens ≥768px tall

### Scenario 2: GNOME Detected, No NVIDIA
- Shows: Base structure + Optional Features (GNOME extension checkbox only)
- Window: 580x1020px
- Button: "Let's Go!" (centered, 200x40px)
- Test file: `test_welcome_scenario2_final.py`
- **Behavior:** Opens full size, no scrolling on screens ≥1080px tall

### Scenario 3: NVIDIA Detected, No GNOME
- Shows: Base structure + Optional Features (CUDA checkbox only)
- Window: 580x1020px
- Button: "Let's Go!" (centered, 200x40px)
- Test file: `test_welcome_scenario3.py`
- **Behavior:** Opens full size, no scrolling on screens ≥1080px tall

### Scenario 4: NVIDIA + GNOME Detected
- Shows: Base structure + Optional Features (both GNOME and CUDA checkboxes)
- Window: 580x1220px (tallest for both options)
- Button: "Let's Go!" (centered, 200x40px)
- Test file: `test_welcome_scenario4.py`
- **Behavior:** Opens full size, no scrolling on screens ≥1280px tall; scrolls smoothly on smaller screens

---

## Button Strategy

**ALL scenarios use "Let's Go!" button** for consistency.

Reasoning:
- Maintains uniform user experience
- Same energy/tone across all welcome screens
- Checkbox opt-in/opt-out handles the choice mechanism
- No multi-step wizard - this is a single adaptive welcome screen
- Everyone proceeds to hotkey testing afterward

---

## Key Implementation Notes

1. **Text Sizes:**
   - Header: `size="x-large"`
   - Subtitle: `size="medium"`
   - Main description: `size="medium"`
   - Section headers (Key Features, Quick Start): `size="large"`
   - Feature/tip items: default/medium size (NOT small)
   - "Next:" text: `size="medium"` for visibility

2. **Margins:**
   - Content margins: 20-30px all sides
   - Left indent for features/tips: 20px
   - Spacing between sections: 15px

3. **Scrollable Content (Small Screen Support):**
   - All scenarios wrapped in Gtk.ScrolledWindow
   - Policy: NEVER horizontal, AUTOMATIC vertical
   - No min/max content height constraints - let GTK size naturally
   - Dialog sizes: 700px (scenario 1), 1000px (scenarios 2-3), 1100px (scenario 4)
   - On large screens: Dialog opens at full size, no scrolling needed
   - On small screens (< dialog height): Content scrolls smoothly
   - Overlay scrollbars (thin, semi-transparent) for minimal UI intrusion

4. **No "Skip Setup" Button:**
   - Removed because checkbox handles opt-in/opt-out
   - Hotkey testing is mandatory for all users
   - Only one button: "Let's Go!"

5. **Preferences Note:**
   - Include "→ Advanced" arrow in note
   - Full text: "💡 You can install or change these anytime in Preferences → Advanced"

---

## Reference Screenshot

See: `/home/ron/Pictures/Screenshots/Screenshot From 2025-10-16 19-12-16.png`

This screenshot shows the EXACT layout that ALL scenarios should follow:
- Left window: Scenario 1 (base only)
- Right window: Scenario 2 (base + GNOME extension)

The base structure (header through Quick Start) is IDENTICAL in both windows.

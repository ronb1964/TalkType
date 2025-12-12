# TalkType GNOME Extension - Future Enhancement

## Overview

A companion GNOME Shell extension that unlocks advanced features on GNOME/Wayland environments. **Optional** and downloaded/installed automatically similar to CUDA libraries.

---

## Why a GNOME Extension?

### The Problem
Wayland's security model prevents applications from:
- ❌ Getting global cursor position
- ❌ Positioning windows at specific coordinates
- ❌ Detecting active windows
- ❌ Accessing certain system information

### The Solution
A GNOME Shell extension runs **inside** the compositor with full privileges, enabling features impossible for regular applications.

---

## Features Unlocked by Extension

### 🎯 **1. Positioning & Placement**
- ✅ **Real cursor position** - Indicator appears exactly where you're typing
- ✅ **Active window detection** - Know which app you're dictating into
- ✅ **Smart positioning** - Avoid placing indicator over text field
- ✅ **Follow cursor mode** - Indicator moves as cursor moves
- ✅ **Active text field detection** - Position near actual input focus

### 🎨 **2. Visual Enhancements**
- ✅ **Top bar integration** - Show recording status in GNOME top bar
- ✅ **Panel icon animation** - Pulse/glow when recording
- ✅ **OSD (On-Screen Display)** - Native GNOME-style overlays
- ✅ **Quick Settings integration** - Toggle in Quick Settings panel
- ✅ **Custom notification area** - Better than standard notifications

### ⚡ **3. Workflow Integration**
- ✅ **App-specific settings** - Different behavior per application
  - Example: Auto-disable in password fields
  - Example: Different model per app (browser vs code editor)
- ✅ **Workspace awareness** - Only activate on certain workspaces
- ✅ **Quick actions menu** - Right-click top bar for controls
- ✅ **Global keyboard shortcuts** - Beyond what apps can register

### 🧠 **4. Smart Features**
- ✅ **Auto-pause detection** - Pause when switching apps
- ✅ **Context awareness** - Know if you're in password/private field
- ✅ **Window focus management** - Prevent indicator from stealing focus
- ✅ **Multi-monitor support** - Know which monitor cursor is on
- ✅ **Screen edge detection** - Never place indicator off-screen

### 🖥️ **5. Desktop Integration**
- ✅ **Quick Settings toggle** - Native toggle in system menu
- ✅ **Activities search** - Find "dictation" in Activities
- ✅ **Auto-start integration** - Better than .desktop files
- ✅ **Session restore** - Remember state across logout/login
- ✅ **System settings integration** - Appear in GNOME Settings

### 🎤 **6. Advanced Audio**
- ✅ **Microphone source visualization** - Show which mic in top bar
- ✅ **Live audio level** - Visual feedback in panel
- ✅ **Background noise detection** - Warn if environment too noisy
- ✅ **Automatic mic selection** - Switch to best available mic

---

## Technical Implementation

### Extension Architecture

```
talktype-extension@ronb1964.github.io/
├── extension.js          # Main extension code (~200 lines)
├── metadata.json         # Extension info & compatibility
├── prefs.js             # Optional: Extension preferences
├── stylesheet.css       # Optional: Custom styling
└── schemas/             # Optional: GSettings schema
    └── org.gnome.shell.extensions.talktype.gschema.xml
```

### DBus Interface

The extension exposes methods via DBus that TalkType calls:

```javascript
// Extension exposes:
interface org.talktype.Helper {
    // Get current cursor position
    GetCursorPosition() -> (int x, int y)

    // Get active window info
    GetActiveWindow() -> (int x, int y, int width, int height, string app_name)

    // Get focused text field position (if available)
    GetTextFieldPosition() -> (int x, int y, int width, int height)

    // Show/hide recording indicator at position
    ShowIndicator(int x, int y, string size)
    HideIndicator()

    // Update indicator with audio level
    UpdateAudioLevel(double level)

    // Top bar integration
    SetRecordingStatus(boolean recording, int elapsed_seconds)
}
```

### TalkType Integration

```python
# In app.py - Check for extension availability
def check_gnome_extension():
    """Check if TalkType GNOME extension is available"""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        proxy = Gio.DBusProxy.new_sync(
            bus,
            Gio.DBusProxyFlags.NONE,
            None,
            'org.talktype.Helper',
            '/org/talktype/Helper',
            'org.talktype.Helper',
            None
        )
        # Extension is available
        return True
    except:
        return False

# On first run - Offer to install extension
def offer_extension_install():
    if is_gnome_wayland() and not extension_installed():
        dialog = show_dialog(
            "Enhanced GNOME Features Available",
            "TalkType can download a GNOME extension that enables:\n"
            "• Accurate cursor tracking\n"
            "• Smart indicator positioning\n"
            "• Top bar integration\n"
            "\nDownload and install? (Requires GNOME Extensions app)"
        )
        if dialog.run() == RESPONSE_YES:
            download_and_install_extension()
```

---

## Installation Flow

### Automatic Installation (Like CUDA Download)

1. **Detection Phase**
   ```python
   if is_gnome() and is_wayland():
       if not extension_exists():
           show_extension_offer_dialog()
   ```

2. **Download Phase**
   - Download from GitHub releases: `talktype-extension-v1.0.zip`
   - Extract to: `~/.local/share/gnome-shell/extensions/talktype@ronb1964.github.io/`
   - Verify files extracted correctly

3. **Enable Phase**
   - Show notification: "Extension installed! Please enable it."
   - Open GNOME Extensions app automatically (if available)
   - Or provide manual instruction

4. **Verification Phase**
   - Check if extension is enabled via DBus
   - Show success/failure message
   - Gracefully degrade if not enabled

### Manual Installation (Fallback)

```bash
# User can also install manually
cd ~/.local/share/gnome-shell/extensions/
wget https://github.com/ronb1964/TalkType/releases/download/v0.5.0/talktype-extension-v1.0.zip
unzip talktype-extension-v1.0.zip
gnome-extensions enable talktype@ronb1964.github.io
```

---

## Extension Code Complexity

### Basic Extension (Cursor Position Only)
**~50 lines of JavaScript**

```javascript
const { GLib, Gio } = imports.gi;
const Main = imports.ui.main;

class Extension {
    enable() {
        this._dbus = Gio.DBusExportedObject.wrapJSObject(
            DBUS_INTERFACE_XML,
            {
                GetCursorPosition: () => {
                    let [x, y] = global.get_pointer();
                    return [x, y];
                }
            }
        );
        this._dbus.export(Gio.DBus.session, '/org/talktype/Helper');
    }

    disable() {
        this._dbus.unexport();
    }
}

function init() {
    return new Extension();
}
```

### Full-Featured Extension (All Features)
**~300-500 lines of JavaScript**

Still very manageable! Compare to:
- Recording indicator: ~400 lines of Python
- Preferences UI: ~700 lines of Python

---

## GNOME Version Compatibility

### Challenge
Different GNOME versions have slightly different APIs

### Solution
Support matrix in `metadata.json`:

```json
{
  "name": "TalkType Helper",
  "description": "Enables advanced TalkType features on GNOME/Wayland",
  "uuid": "talktype@ronb1964.github.io",
  "shell-version": [
    "42",
    "43",
    "44",
    "45",
    "46"
  ],
  "version": 1,
  "url": "https://github.com/ronb1964/TalkType"
}
```

### Testing Strategy
- Primary: GNOME 45/46 (current)
- Secondary: GNOME 43/44 (Ubuntu 22.04/23.04)
- Graceful degradation for unsupported versions

---

## Desktop Environment Compatibility

### Current AppImage Compatibility Matrix

| Desktop Environment | Wayland | X11 | Notes |
|---------------------|---------|-----|-------|
| **GNOME** | ✅ Works | ✅ Works | Extension adds features on Wayland |
| **KDE Plasma** | ✅ Works | ✅ Works | No extension needed (KWin has better APIs) |
| **Xfce** | N/A | ✅ Works | X11 only |
| **MATE** | N/A | ✅ Works | X11 only |
| **Cinnamon** | ⚠️ Limited | ✅ Works | Wayland experimental |
| **Budgie** | ⚠️ Limited | ✅ Works | Wayland experimental |
| **LXQt** | ⚠️ Limited | ✅ Works | Basic Wayland support |
| **Sway** | ✅ Works | N/A | Wayland native compositor |
| **Hyprland** | ✅ Works | N/A | Wayland native compositor |

### What Works Everywhere

**Core Features (No Extension Needed):**
- ✅ Voice transcription
- ✅ Text injection
- ✅ Hotkey activation
- ✅ Voice commands
- ✅ System tray
- ✅ Preferences UI
- ✅ Model selection
- ✅ CUDA support

**Recording Indicator:**
- ✅ Shows and animates everywhere
- ✅ User-configurable size
- ⚠️ Positioning: Works on X11, center-only on most Wayland
- ✅ Extension enables positioning on GNOME/Wayland

**Bottom Line:**
TalkType works on **all major Linux DEs**. The extension just adds **bonus features** for GNOME users.

---

## Extension Development Workflow

### Phase 1: Prototype (1-2 days)
- Create basic extension structure
- Implement cursor position DBus method
- Test on GNOME 45/46

### Phase 2: Core Features (3-5 days)
- Add active window detection
- Implement indicator positioning
- Top bar integration
- Test on multiple GNOME versions

### Phase 3: Polish (2-3 days)
- Add preferences UI (optional)
- Improve error handling
- Write documentation
- Create installation instructions

### Phase 4: Integration (2-3 days)
- Add auto-download to TalkType
- Implement detection logic
- Test installation flow
- Update AppImage build

**Total Estimated Time: 1-2 weeks**

---

## Risks & Mitigations

### Risk 1: GNOME API Changes
**Mitigation:**
- Test on multiple GNOME versions
- Use compatibility checks
- Graceful degradation

### Risk 2: Extension Gets Disabled
**Mitigation:**
- TalkType detects and warns user
- Falls back to non-extension mode
- Clear instructions to re-enable

### Risk 3: User Doesn't Install Extension
**Mitigation:**
- Extension is **optional**
- TalkType works perfectly without it
- Just shows "enhanced features available" once

### Risk 4: Maintenance Burden
**Mitigation:**
- Keep extension simple (~300 lines)
- Minimal dependencies
- Community can help maintain

---

## Alternative: KDE Plasma

Good news! KDE Plasma already has better APIs:

```javascript
// KWin script can do this without extension complexity
workspace.cursorPos  // Gets cursor position
workspace.activeClient  // Gets active window
```

Could create a similar helper for KDE, but it's less critical since KDE's Wayland implementation is more permissive.

---

## Roadmap Placement

### Recommended Timeline

**v0.4.0** (Next)
- Focus on polish and core features
- No extension yet

**v0.5.0** (2-3 months)
- GNOME Extension development
- Auto-download implementation
- Enhanced indicator positioning

**v0.6.0+**
- KDE helper (if needed)
- Additional extension features
- Cross-DE improvements

---

## Benefits Summary

### For Users
- ✅ Better experience on GNOME/Wayland
- ✅ Native desktop integration
- ✅ Optional (doesn't break other DEs)
- ✅ Auto-installed (like CUDA libs)

### For Development
- ✅ Solves Wayland positioning problem
- ✅ Opens door for advanced features
- ✅ Relatively simple to implement
- ✅ Well-scoped project

### For TalkType
- ✅ First-class GNOME citizen
- ✅ Competitive advantage
- ✅ Shows polish and attention to detail
- ✅ Community contribution potential

---

## Next Steps

1. ✅ Finish current AppImage polish (v0.4.0)
2. ✅ Get stable release out
3. ✅ Gather user feedback on GNOME
4. 🔄 Prototype basic extension
5. 🔄 Test on multiple GNOME versions
6. 🔄 Implement auto-download
7. 🔄 Release as v0.5.0

---

## Resources

- **GNOME Shell Extension Docs:** https://gjs.guide/extensions/
- **GJS (GNOME JavaScript) Guide:** https://gjs-docs.gnome.org/
- **Extension Examples:** https://extensions.gnome.org/
- **DBus Specification:** https://www.freedesktop.org/wiki/Software/dbus/
- **GNOME Shell Source:** https://gitlab.gnome.org/GNOME/gnome-shell

---

*Document created: 2025-10-14*
*Last updated: 2025-10-14*

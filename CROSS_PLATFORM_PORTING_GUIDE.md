# TalkType Cross-Platform Porting Guide

## Current State: Linux Wayland Only

TalkType is currently built specifically for **Linux with Wayland**, using platform-specific technologies.

## Platform-Specific Dependencies

### Core Challenges

#### 1. **Text Injection (Critical)**
**Current (Linux Wayland):**
- `ydotool` - Wayland keystroke injector
- `wtype` - Alternative Wayland typing tool
- `wl-clipboard` - Wayland clipboard manager

**macOS Alternatives:**
- `pyautogui` - Cross-platform keyboard automation
- `pynput` - Cross-platform input control
- `AppKit` - Native macOS framework (NSEvent)
- `Quartz` - macOS Core Graphics framework

**Windows Alternatives:**
- `pyautogui` - Cross-platform keyboard automation
- `pynput` - Cross-platform input control
- `pywinauto` - Windows automation
- `ctypes` with Windows API (SendInput)

#### 2. **Hotkey Detection (Critical)**
**Current (Linux):**
- `evdev` - Linux input device handling
- Requires low-level device access

**macOS Alternatives:**
- `pynput` - Global hotkey listener
- `keyboard` library (with sudo on macOS)
- `AppKit` NSEvent global monitor

**Windows Alternatives:**
- `pynput` - Global hotkey listener
- `keyboard` library
- `pywinauto` with Windows hooks

#### 3. **System Tray (Moderate)**
**Current (Linux):**
- `pygobject` (GTK 3) with AppIndicator
- Wayland-specific implementation

**macOS Alternatives:**
- `rumps` (Ridiculously Uncomplicated macOS Python Statusbar apps)
- `pystray` - Cross-platform system tray
- `PyQt5/PyQt6` QSystemTrayIcon
- `wxPython` TaskBarIcon

**Windows Alternatives:**
- `pystray` - Cross-platform system tray
- `PyQt5/PyQt6` QSystemTrayIcon
- `infi.systray`
- `wxPython` TaskBarIcon

#### 4. **GUI Framework (Moderate)**
**Current (Linux):**
- GTK 3 via `pygobject`
- Wayland dialogs and windows

**Cross-Platform Alternatives:**
- `PyQt5/PyQt6` - Most professional, cross-platform
- `tkinter` - Built-in Python, cross-platform (but basic)
- `wxPython` - Native look on all platforms
- `Kivy` - Modern, cross-platform

## Porting Strategy

### Option 1: Cross-Platform Rewrite (Recommended)
**Effort: High (2-4 weeks)**

Complete rewrite using cross-platform libraries:

```python
# Dependencies for cross-platform version
pyautogui         # Text injection (all platforms)
pynput            # Hotkey detection (all platforms)
pystray           # System tray (all platforms)
PyQt6             # GUI framework (all platforms)
faster-whisper    # ✓ Already cross-platform
sounddevice       # ✓ Already cross-platform
torch             # ✓ Already cross-platform
```

**Pros:**
- Single codebase for all platforms
- Modern, maintainable
- Easier to support

**Cons:**
- Complete rewrite required
- May lose some Linux-specific optimizations
- Need to test on all platforms

### Option 2: Platform Abstraction Layer
**Effort: Medium (1-2 weeks)**

Keep current code but add platform detection and abstraction:

```python
# Example structure
talktype/
  platforms/
    __init__.py      # Platform detection
    linux.py         # Current ydotool/evdev implementation
    macos.py         # macOS NSEvent/AppKit implementation
    windows.py       # Windows SendInput implementation
  core/
    transcription.py # ✓ Platform-independent (Whisper)
    audio.py         # ✓ Platform-independent (sounddevice)
```

**Pros:**
- Keep optimized Linux implementation
- Gradual porting
- Platform-specific features possible

**Cons:**
- More complex codebase
- Multiple code paths to maintain
- More testing required

### Option 3: Electron/Web Wrapper
**Effort: Medium (2-3 weeks)**

Wrap core Python backend with Electron frontend:

- Python backend handles Whisper transcription
- Electron frontend handles UI and system integration
- IPC between Python and JavaScript

**Pros:**
- Single UI codebase (HTML/CSS/JS)
- Native-looking on all platforms
- Easy distribution

**Cons:**
- Larger app size
- More dependencies
- Less "native" feel

## Detailed Porting Steps

### For macOS

1. **Replace evdev hotkey detection:**
   ```python
   from pynput import keyboard

   def on_press(key):
       if key == keyboard.Key.f8:
           start_recording()

   listener = keyboard.Listener(on_press=on_press)
   listener.start()
   ```

2. **Replace ydotool text injection:**
   ```python
   import pyautogui
   # or
   from AppKit import NSPasteboard, NSStringPboardType
   from Quartz import CGEventCreateKeyboardEvent, CGEventPost
   ```

3. **Replace GTK tray:**
   ```python
   import rumps
   # or
   from pystray import Icon, Menu, MenuItem
   ```

4. **Package as .app:**
   - Use `py2app` or `PyInstaller`
   - Include Python runtime
   - Bundle Whisper models or download on first run

### For Windows

1. **Replace evdev hotkey detection:**
   ```python
   from pynput import keyboard
   # Same as macOS
   ```

2. **Replace ydotool text injection:**
   ```python
   import pyautogui
   # or
   import ctypes
   # Use SendInput Windows API
   ```

3. **Replace GTK tray:**
   ```python
   from pystray import Icon, Menu, MenuItem
   # or PyQt6 QSystemTrayIcon
   ```

4. **Package as .exe:**
   - Use `PyInstaller` or `cx_Freeze`
   - Include MSVC runtime
   - Bundle CUDA for GPU support (optional)

## Complexity Assessment

### Easy to Port (Already Cross-Platform ✓)
- ✅ Whisper transcription (faster-whisper)
- ✅ Audio recording (sounddevice)
- ✅ PyTorch/CUDA (works on all platforms)
- ✅ Text processing/normalization
- ✅ Configuration management

### Moderate Effort
- ⚠️ GUI/Preferences window (need cross-platform framework)
- ⚠️ System tray (need cross-platform library)
- ⚠️ First-run setup

### High Effort (Platform-Specific)
- ❌ Hotkey detection (evdev → platform-specific replacement)
- ❌ Text injection (ydotool → platform-specific replacement)
- ❌ Wayland-specific features

## Recommended Approach

### Phase 1: Proof of Concept (1 week)
1. Create minimal cross-platform version using:
   - `pynput` for hotkeys
   - `pyautogui` for text injection
   - `pystray` for system tray
2. Test basic dictation on macOS or Windows
3. Validate Whisper performance

### Phase 2: Full Implementation (2-3 weeks)
1. Implement complete GUI with PyQt6
2. Add preferences/settings
3. Platform-specific optimizations
4. First-run setup for each platform

### Phase 3: Distribution (1 week)
1. Create installers:
   - macOS: `.dmg` with `py2app`
   - Windows: `.exe` with PyInstaller + InnoSetup
2. Code signing (macOS/Windows)
3. Auto-update mechanism

### Phase 4: Testing & Polish (1-2 weeks)
1. Platform-specific testing
2. Bug fixes
3. Performance optimization
4. Documentation

## Total Estimated Effort

- **Minimum (basic port):** 2-3 weeks
- **Full-featured:** 4-6 weeks
- **Production-ready:** 6-8 weeks

## Alternative: Contribute to Existing Projects

Instead of porting, consider:
- **Talon** - Mature voice control for all platforms (but paid)
- **Rhasspy** - Open-source voice assistant (Linux-focused)
- Contributing Linux Wayland support to existing cross-platform tools

## Key Dependencies Matrix

| Feature | Linux (Current) | macOS | Windows |
|---------|----------------|-------|---------|
| **Hotkeys** | evdev | pynput/NSEvent | pynput/WinAPI |
| **Text Injection** | ydotool/wtype | pyautogui/AppKit | pyautogui/SendInput |
| **System Tray** | GTK/AppIndicator | rumps/pystray | pystray/PyQt |
| **GUI** | GTK 3 | PyQt6/tkinter | PyQt6/tkinter |
| **Audio** | sounddevice ✓ | sounddevice ✓ | sounddevice ✓ |
| **Whisper** | faster-whisper ✓ | faster-whisper ✓ | faster-whisper ✓ |
| **GPU** | CUDA ✓ | Metal (MPS) | CUDA/DirectML ✓ |

## Recommended Cross-Platform Stack

```toml
[tool.poetry.dependencies]
python = ">=3.10,<3.14"
faster-whisper = "*"
sounddevice = "*"
torch = "*"                    # ✓ Cross-platform
numpy = "*"                    # ✓ Cross-platform
pyperclip = "*"                # ✓ Cross-platform
PyQt6 = "*"                    # GUI (all platforms)
pynput = "*"                   # Hotkeys (all platforms)
pystray = "*"                  # System tray (all platforms)
pyautogui = "*"                # Text injection (all platforms)

# Platform-specific
[tool.poetry.dependencies.pyobjc]
version = "*"
markers = "sys_platform == 'darwin'"  # macOS only

[tool.poetry.dependencies.pywin32]
version = "*"
markers = "sys_platform == 'win32'"   # Windows only
```

## Next Steps

1. **Decision:** Choose porting strategy (rewrite vs. abstraction)
2. **Prototype:** Build minimal working version on target platform
3. **Validate:** Test core functionality (hotkeys, typing, transcription)
4. **Iterate:** Add features incrementally
5. **Package:** Create platform-specific installers
6. **Distribute:** App Store (macOS), Microsoft Store (Windows), or direct download

## Resources

- **PyQt6 Documentation:** https://doc.qt.io/qtforpython/
- **pynput Documentation:** https://pynput.readthedocs.io/
- **pystray Documentation:** https://pystray.readthedocs.io/
- **PyInstaller:** https://pyinstaller.org/
- **py2app (macOS):** https://py2app.readthedocs.io/

## Conclusion

Porting TalkType to macOS/Windows is **definitely feasible** with moderate effort (4-8 weeks). The AI transcription core is already cross-platform; the main work is replacing Linux-specific input/output mechanisms with cross-platform alternatives.

The biggest challenges are:
1. Reliable hotkey detection across platforms
2. Universal text injection that works in all apps
3. Native system tray integration

Recommended path: **Phase 1 proof-of-concept** to validate the approach, then commit to full implementation if successful.

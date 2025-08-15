# TalkType Flatpak Build Guide

This guide explains how to build and install TalkType as a Flatpak package.

## ⚠️ Important Limitations

**TalkType as a Flatpak has significant limitations due to its requirements:**

1. **Input Device Access**: TalkType needs direct access to input devices (`/dev/input/*`) for global hotkey detection, which conflicts with Flatpak's sandboxing
2. **System Integration**: Requires systemd service management and low-level system access
3. **ydotool Dependency**: Needs ydotool for Wayland text injection, which requires elevated permissions

**Recommendation**: For full functionality, install TalkType via pip or use the native systemd service instead of Flatpak.

## Prerequisites

Install Flatpak and required tools:
```bash
sudo apt install flatpak flatpak-builder
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install flathub org.freedesktop.Platform//23.08 org.freedesktop.Sdk//23.08
```

## Building the Flatpak

1. **Clone and prepare the repository:**
   ```bash
   git clone https://github.com/ronb1964/TalkType.git
   cd TalkType
   ```

2. **Generate dependency modules (optional, for exact versions):**
   ```bash
   pip install req2flatpak
   req2flatpak --requirements-file requirements.txt --target-platforms 310-x86_64 310-aarch64 > python-modules.json
   ```

3. **Build the Flatpak:**
   ```bash
   flatpak-builder --force-clean build-dir io.github.ronb1964.TalkType.json
   ```

4. **Test the build:**
   ```bash
   flatpak-builder --run build-dir io.github.ronb1964.TalkType.json dictate-tray
   ```

5. **Install locally:**
   ```bash
   flatpak-builder --user --install --force-clean build-dir io.github.ronb1964.TalkType.json
   ```

6. **Create distributable bundle:**
   ```bash
   flatpak build-bundle ~/.local/share/flatpak/repo talktype.flatpak io.github.ronb1964.TalkType
   ```

## Known Issues with Flatpak Version

- **Limited input device access**: Global hotkeys may not work
- **No systemd integration**: Service management not available
- **Reduced text injection capabilities**: May fallback to clipboard-only mode
- **Permissions conflicts**: Some features require elevated access

## Permissions Granted

The Flatpak manifest includes these permissions:
- `--device=all`: Access to input devices (limited by Flatpak)
- `--socket=pulseaudio`: Audio recording
- `--socket=wayland` / `--socket=x11`: Display access
- `--system-talk-name=org.freedesktop.systemd1`: systemd communication (limited)
- `--talk-name=org.freedesktop.Notifications`: Desktop notifications

## Alternative Installation

For full functionality, consider these alternatives:

1. **pip installation** (recommended):
   ```bash
   pip install --user -e .
   ```

2. **Native package**: Look for distribution-specific packages

3. **AppImage**: More suitable for this type of system integration

## Flathub Submission

To submit to Flathub:
1. Fork https://github.com/flathub/flathub
2. Create a new repository for `io.github.ronb1964.TalkType`
3. Submit the manifest with required metadata
4. Address any review feedback

Note: Flathub may reject applications requiring extensive system access.

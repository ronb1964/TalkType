# TalkType GNOME Extension

Native GNOME Shell integration for TalkType speech recognition.

## Features

- **Panel Indicator** - Shows recording state in GNOME top bar
- **Quick Model Switcher** - Change Whisper models from the panel menu
- **Service Control** - Start/stop dictation service
- **Visual Feedback** - Icon changes color when recording
- **D-Bus Integration** - Communicates with TalkType Python backend

## Installation

### Option 1: Manual Installation (Development)

```bash
# From TalkType project root
cd gnome-extension
cp -r talktype@ronb1964.github.io ~/.local/share/gnome-shell/extensions/
```

Then:
1. Log out and log back in (or restart GNOME Shell with Alt+F2, type `r`, press Enter)
2. Enable the extension:
   ```bash
   gnome-extensions enable talktype@ronb1964.github.io
   ```

### Option 2: Install from ZIP

```bash
# Build extension package
cd gnome-extension
zip -r talktype@ronb1964.github.io.zip talktype@ronb1964.github.io/

# Install
gnome-extensions install talktype@ronb1964.github.io.zip
gnome-extensions enable talktype@ronb1964.github.io
```

## Usage

1. **Start TalkType Python backend** first:
   ```bash
   ./TalkType-v0.3.7-x86_64.AppImage
   ```
   Or if installed:
   ```bash
   talktype-tray
   ```

2. **Extension will automatically connect** to the D-Bus service

3. **Click the microphone icon** in the top panel to:
   - Toggle dictation service on/off
   - Switch between Whisper models
   - Open preferences

## Requirements

- GNOME Shell 45-48
- TalkType Python backend running with D-Bus service
- Wayland session

## Troubleshooting

### Extension not appearing

```bash
# Check if extension is installed
gnome-extensions list | grep talktype

# Check extension logs
journalctl -f -o cat /usr/bin/gnome-shell

# Restart GNOME Shell
Alt+F2 → type 'r' → Enter
```

### D-Bus connection issues

```bash
# Check if TalkType D-Bus service is running
dbus-send --session --print-reply \
  --dest=io.github.ronb1964.TalkType \
  /io/github/ronb1964/TalkType \
  io.github.ronb1964.TalkType.GetStatus
```

## Development

### Testing

```bash
# Watch extension logs
journalctl -f -o cat /usr/bin/gnome-shell | grep -i talktype

# Reload extension after changes
gnome-extensions disable talktype@ronb1964.github.io
gnome-extensions enable talktype@ronb1964.github.io
```

### Debugging D-Bus

```bash
# Monitor D-Bus signals
dbus-monitor --session "interface='io.github.ronb1964.TalkType'"
```

## Future Features

- [ ] On-Screen Display (OSD) for recording state
- [ ] Visual waveform during recording
- [ ] Quick settings integration (GNOME 43+)
- [ ] Keyboard shortcuts integration
- [ ] Session statistics display

## License

MIT License - Same as TalkType parent project

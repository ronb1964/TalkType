#!/usr/bin/env python3
"""Regenerate autostart file with improved portable launch command."""

import os
import subprocess
import sys

def get_launch_command():
    """Get the appropriate launch command for TalkType."""
    # Check if dictate-tray command is available in PATH
    try:
        result = subprocess.run(
            ['which', 'dictate-tray'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            dictate_tray_path = result.stdout.strip()
            # Verify it's executable
            if os.path.isfile(dictate_tray_path) and os.access(dictate_tray_path, os.X_OK):
                return dictate_tray_path
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback: use current Python interpreter
    python_path = sys.executable
    # Use -m to run as module, which is more reliable
    return f'{python_path} -m talktype.tray'

def get_icon_path():
    """Get the path to the TalkType icon."""
    # Try common locations
    possible_paths = [
        # Official icon in development location
        'icons/OFFICIAL_ICON_DO_NOT_CHANGE.svg',
        # AppImage location
        os.path.join(os.path.dirname(sys.executable), '..', 'io.github.ronb1964.TalkType.svg'),
        # Old development location
        'AppDir/io.github.ronb1964.TalkType.svg',
        # Installed location
        '/usr/share/icons/hicolor/scalable/apps/io.github.ronb1964.TalkType.svg',
        '/usr/local/share/icons/hicolor/scalable/apps/io.github.ronb1964.TalkType.svg',
    ]

    for path in possible_paths:
        if os.path.isfile(path):
            return os.path.abspath(path)

    # Fallback to system icon name
    return 'audio-input-microphone'

def main():
    autostart_dir = os.path.expanduser("~/.config/autostart")
    desktop_file = os.path.join(autostart_dir, "talktype.desktop")

    # Create autostart directory if it doesn't exist
    os.makedirs(autostart_dir, exist_ok=True)

    # Get launch command and icon
    exec_cmd = get_launch_command()
    icon_path = get_icon_path()

    print("Regenerating autostart file...")
    print(f"  Launch command: {exec_cmd}")
    print(f"  Icon path: {icon_path}")

    # Create desktop file content
    desktop_content = f"""[Desktop Entry]
Type=Application
Name=TalkType
GenericName=Voice Dictation
Comment=AI-powered dictation for Wayland using Faster-Whisper
Exec={exec_cmd}
Icon={icon_path}
Terminal=false
Categories=Utility;
Keywords=dictation;voice;speech;whisper;ai;transcription;
StartupNotify=true
StartupWMClass=TalkType
X-GNOME-Autostart-enabled=true
"""

    try:
        with open(desktop_file, "w") as f:
            f.write(desktop_content)
        print(f"\n✅ Created autostart file: {desktop_file}")
        print("\nFile contents:")
        print("=" * 60)
        print(desktop_content)
        print("=" * 60)
    except Exception as e:
        print(f"❌ Failed to create autostart file: {e}")
        return 1

    return 0

if __name__ == '__main__':
    sys.exit(main())

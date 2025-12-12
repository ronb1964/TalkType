#!/usr/bin/env python3
"""Regenerate autostart file for DEV_MODE."""

import os
import sys

# Set DEV_MODE
os.environ['DEV_MODE'] = '1'

# Set PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
sys.path.insert(1, '/usr/lib64/python3.13/site-packages')
sys.path.insert(2, '/usr/lib/python3.13/site-packages')

from talktype import config

def get_launch_command():
    """Get launch command for DEV_MODE."""
    if config.DEV_MODE:
        # Find the run-dev.sh script
        project_root = os.path.dirname(os.path.abspath(__file__))
        run_dev_script = os.path.join(project_root, 'run-dev.sh')
        if os.path.isfile(run_dev_script) and os.access(run_dev_script, os.X_OK):
            return run_dev_script
        else:
            # Fallback for dev mode - use bash with env vars
            python_path = sys.executable
            return f'/bin/bash -c "cd {project_root} && DEV_MODE=1 PYTHONPATH=./src:/usr/lib64/python3.13/site-packages:/usr/lib/python3.13/site-packages {python_path} -m talktype.tray"'

    # Fallback
    return f'{sys.executable} -m talktype.tray'

def get_icon_path():
    """Get icon path."""
    project_root = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(project_root, 'icons', 'OFFICIAL_ICON_DO_NOT_CHANGE.svg')
    if os.path.isfile(icon_path):
        return icon_path
    return 'audio-input-microphone'

def main():
    autostart_dir = os.path.expanduser("~/.config/autostart")
    desktop_file = os.path.join(autostart_dir, "talktype.desktop")

    # Create autostart directory if it doesn't exist
    os.makedirs(autostart_dir, exist_ok=True)

    # Get launch command and icon
    exec_cmd = get_launch_command()
    icon_path = get_icon_path()

    print("Regenerating autostart file for DEV_MODE...")
    print(f"  DEV_MODE: {config.DEV_MODE}")
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

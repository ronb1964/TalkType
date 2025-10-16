#!/usr/bin/env python3
"""
Desktop environment detection for TalkType
"""

import os
import subprocess
from typing import Optional


def get_desktop_environment() -> str:
    """
    Detect the current desktop environment

    Returns:
        str: Desktop environment name ('gnome', 'kde', 'xfce', 'unknown')
    """
    # Check environment variables
    desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
    session = os.environ.get('DESKTOP_SESSION', '').lower()

    # GNOME
    if 'gnome' in desktop or 'gnome' in session:
        return 'gnome'

    # KDE Plasma
    if 'kde' in desktop or 'plasma' in desktop or 'kde' in session:
        return 'kde'

    # XFCE
    if 'xfce' in desktop or 'xfce' in session:
        return 'xfce'

    # Cinnamon
    if 'cinnamon' in desktop or 'cinnamon' in session:
        return 'cinnamon'

    # MATE
    if 'mate' in desktop or 'mate' in session:
        return 'mate'

    return 'unknown'


def is_gnome() -> bool:
    """Check if running GNOME desktop"""
    return get_desktop_environment() == 'gnome'


def get_gnome_shell_version() -> Optional[str]:
    """
    Get GNOME Shell version

    Returns:
        str: Version string (e.g., "48.4") or None if not GNOME
    """
    if not is_gnome():
        return None

    try:
        result = subprocess.run(
            ['gnome-shell', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Output is like "GNOME Shell 48.4"
            version = result.stdout.strip().split()[-1]
            return version
    except (subprocess.TimeoutExpired, FileNotFoundError, IndexError):
        pass

    return None


def is_wayland() -> bool:
    """Check if running on Wayland"""
    session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
    wayland_display = os.environ.get('WAYLAND_DISPLAY', '')

    return 'wayland' in session_type or bool(wayland_display)


def get_extension_dir() -> str:
    """Get GNOME extensions directory"""
    home = os.path.expanduser('~')
    return os.path.join(home, '.local', 'share', 'gnome-shell', 'extensions')


def is_extension_installed(uuid: str) -> bool:
    """
    Check if a GNOME extension is installed

    Args:
        uuid: Extension UUID (e.g., 'talktype@ronb1964.github.io')

    Returns:
        bool: True if extension is installed
    """
    ext_dir = get_extension_dir()
    ext_path = os.path.join(ext_dir, uuid)

    # Check if extension directory exists and has metadata.json
    metadata_path = os.path.join(ext_path, 'metadata.json')
    return os.path.isfile(metadata_path)


def is_extension_enabled(uuid: str) -> bool:
    """
    Check if a GNOME extension is enabled

    Args:
        uuid: Extension UUID

    Returns:
        bool: True if extension is enabled
    """
    try:
        result = subprocess.run(
            ['gnome-extensions', 'info', uuid],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Look for "State: ENABLED" in output
            return 'State: ENABLED' in result.stdout or 'State: ACTIVE' in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return False


def enable_extension(uuid: str) -> bool:
    """
    Enable a GNOME extension

    Args:
        uuid: Extension UUID

    Returns:
        bool: True if successful
    """
    try:
        result = subprocess.run(
            ['gnome-extensions', 'enable', uuid],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


if __name__ == '__main__':
    # Test detection
    print(f"Desktop Environment: {get_desktop_environment()}")
    print(f"Is GNOME: {is_gnome()}")
    print(f"GNOME Shell Version: {get_gnome_shell_version()}")
    print(f"Is Wayland: {is_wayland()}")
    print(f"Extension directory: {get_extension_dir()}")

    uuid = 'talktype@ronb1964.github.io'
    print(f"\nExtension '{uuid}':")
    print(f"  Installed: {is_extension_installed(uuid)}")
    print(f"  Enabled: {is_extension_enabled(uuid)}")

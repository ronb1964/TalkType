"""Launch-at-login (XDG autostart) management, shared by Preferences and onboarding.

Both the Preferences "Launch at login" toggle and first-run onboarding need to
write the same autostart .desktop file with the same launch command. Keeping the
logic here means there is exactly one definition of how TalkType relaunches
itself — the command that a fresh install writes and the command Preferences
writes can never drift apart.

The launch command specifically must resolve to the env-setting wrapper
(`/usr/bin/talktype` → AppRun), not a bare `python3 -m talktype.tray`: the bundled
interpreter has no PYTHONPATH/LD_LIBRARY_PATH/GI_TYPELIB_PATH, so a raw-Python
autostart line dies silently at login with ModuleNotFoundError.
"""

import os
import sys
import glob
import subprocess

from .logger import setup_logger

logger = setup_logger(__name__)


def _project_root() -> str:
    """Repo root, for dev-mode paths. autostart.py is src/talktype/autostart.py."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_launch_command() -> str:
    """Return the most portable command to launch the tray.

    Order: dev script → AppImage path → packaged launcher (absolute) → PATH
    lookup → bare interpreter (last resort). See the module docstring for why the
    packaged launcher must win over a bare-Python invocation.
    """
    from . import config
    if config.DEV_MODE:
        root = _project_root()
        run_dev = os.path.join(root, 'run-dev.sh')
        if os.path.isfile(run_dev) and os.access(run_dev, os.X_OK):
            return run_dev
        return (f'/bin/bash -c "cd {root} && DEV_MODE=1 '
                f'PYTHONPATH=./src:/usr/lib64/python3.13/site-packages:'
                f'/usr/lib/python3.13/site-packages {sys.executable} -m talktype.tray"')

    # Running from an AppImage: relaunch the AppImage itself (defaults to tray).
    appimage_path = os.environ.get('APPIMAGE')
    if appimage_path and os.path.isfile(appimage_path) and os.access(appimage_path, os.X_OK):
        return appimage_path

    # Inside an AppImage mount but APPIMAGE unset: find the AppImage on disk.
    if '/tmp/.mount_' in sys.executable or 'squashfs-root' in sys.executable:
        for pattern in (os.path.expanduser('~/AppImages/TalkType-*.AppImage'),
                        os.path.expanduser('~/Downloads/TalkType-*.AppImage')):
            matches = glob.glob(pattern)
            if matches:
                latest = max(matches, key=os.path.getmtime)
                if os.access(latest, os.X_OK):
                    return latest

    # Installed .deb/.rpm: prefer the KNOWN ABSOLUTE launcher, not `which`
    # (a stray ~/.local/bin/talktype must never be written into autostart).
    for launcher in ("/usr/bin/talktype", "/usr/bin/dictate-tray"):
        if os.path.isfile(launcher) and os.access(launcher, os.X_OK):
            return launcher

    # Non-standard packaged layout: PATH lookup, still preferring the wrapper.
    for cmd in ("talktype", "dictate-tray"):
        try:
            result = subprocess.run(['which', cmd], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                path = result.stdout.strip()
                if os.path.isfile(path) and os.access(path, os.X_OK):
                    return path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Last resort — may lack the bundled environment.
    return f'{sys.executable} -m talktype.tray'


def get_icon_path() -> str:
    """Absolute path to the TalkType icon, or a system icon name as fallback."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = _project_root()
    candidates = [
        os.path.join(root, 'icons', 'OFFICIAL_ICON_DO_NOT_CHANGE.svg'),
        os.path.join(os.path.dirname(sys.executable), '..', 'io.github.ronb1964.TalkType.svg'),
        os.path.join(root, 'AppDir', 'io.github.ronb1964.TalkType.svg'),
        '/usr/share/icons/hicolor/scalable/apps/io.github.ronb1964.TalkType.svg',
        '/usr/local/share/icons/hicolor/scalable/apps/io.github.ronb1964.TalkType.svg',
    ]
    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)
    return 'audio-input-microphone'


def _autostart_desktop_path() -> str:
    from . import config
    autostart_dir = os.path.expanduser("~/.config/autostart")
    filename = "talktype-dev.desktop" if config.DEV_MODE else "talktype.desktop"
    return os.path.join(autostart_dir, filename)


def set_autostart(enable: bool) -> bool:
    """Create or disable the autostart .desktop file. Returns True on success.

    Disabling writes a `Hidden=true` stub rather than deleting the file — more
    reliable across desktops (KDE caches entries), and it overrides any existing
    entry.
    """
    from . import config
    desktop_file = _autostart_desktop_path()
    autostart_dir = os.path.dirname(desktop_file)

    try:
        os.makedirs(autostart_dir, exist_ok=True)
    except Exception as e:
        logger.error(f"Could not create autostart dir: {e}")
        return False

    if enable:
        exec_cmd = get_launch_command()
        icon_path = get_icon_path()
        app_name = "TalkType (Dev)" if config.DEV_MODE else "TalkType"
        comment = ("AI-powered dictation - Development Version" if config.DEV_MODE
                   else "AI-powered dictation for Wayland using Faster-Whisper")
        path_line = f"Path={_project_root()}\n" if config.DEV_MODE else ""
        content = f"""[Desktop Entry]
Type=Application
Name={app_name}
GenericName=Voice Dictation
Comment={comment}
Exec={exec_cmd}
Icon={icon_path}
Terminal=false
Categories=Utility;
Keywords=dictation;voice;speech;whisper;ai;transcription;
StartupNotify=true
StartupWMClass=TalkType
X-GNOME-Autostart-enabled=true
{path_line}"""
        try:
            with open(desktop_file, "w") as f:
                f.write(content)
            logger.info(f"Autostart enabled: {desktop_file} (Exec={exec_cmd})")
            return True
        except Exception as e:
            logger.error(f"Failed to write autostart file: {e}")
            return False

    # Disable: Hidden=true stub.
    try:
        with open(desktop_file, "w") as f:
            f.write("[Desktop Entry]\nType=Application\nName=TalkType\nHidden=true\n")
        logger.info(f"Autostart disabled: {desktop_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to disable autostart file: {e}")
        return False

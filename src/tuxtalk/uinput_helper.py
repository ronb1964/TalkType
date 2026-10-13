#!/usr/bin/env python3
"""
uinput Helper Module for TuxTalk

Handles detection and fixing of /dev/uinput permissions required for
keystroke injection via ydotool on Wayland.

The problem:
- ydotool uses the Linux uinput subsystem to inject keystrokes
- /dev/uinput requires special permissions (usually root, or a group such
  as 'input')
- Without access, typing injection silently fails

The solution:
- Detect if user can access /dev/uinput
- If not, offer an opt-in setup step (via pkexec) that does TWO separate
  things -- the udev rule alone is not enough:
    1. installs a udev rule giving the 'input' group access to /dev/uinput
    2. runs `usermod -a -G input` to actually put the user in that group
- The group change only takes effect after a re-login, which is why setup
  asks the user to log out and back in
"""

import os
import subprocess
import grp
import pwd
import shlex
import shutil
from .logger import setup_logger

logger = setup_logger(__name__)

# The udev rule content that grants access to /dev/uinput.
# It reuses the EXISTING 'input' group rather than creating a new one. That is
# deliberate: /dev/input/event* is already owned by 'input', so a single
# `usermod -a -G input` grants both keystroke injection and hotkey reading.
UDEV_RULE_CONTENT = '''# TuxTalk: Allow users in the 'input' group to access uinput
# This enables ydotool keystroke injection on Wayland
KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
'''

UDEV_RULE_PATH = "/etc/udev/rules.d/99-talktype-uinput.rules"


def check_uinput_exists():
    """
    Check if /dev/uinput device exists.
    
    Returns:
        bool: True if /dev/uinput exists, False otherwise
    """
    exists = os.path.exists("/dev/uinput")
    logger.debug(f"/dev/uinput exists: {exists}")
    return exists


def check_uinput_readable():
    """
    Check if current user can read /dev/uinput.
    
    Returns:
        bool: True if readable, False otherwise
    """
    try:
        readable = os.access("/dev/uinput", os.R_OK)
        logger.debug(f"/dev/uinput readable: {readable}")
        return readable
    except Exception as e:
        logger.warning(f"Error checking /dev/uinput read access: {e}")
        return False


def check_uinput_writable():
    """
    Check if current user can write to /dev/uinput.
    
    Returns:
        bool: True if writable, False otherwise
    """
    try:
        writable = os.access("/dev/uinput", os.W_OK)
        logger.debug(f"/dev/uinput writable: {writable}")
        return writable
    except Exception as e:
        logger.warning(f"Error checking /dev/uinput write access: {e}")
        return False


def check_uinput_permission():
    """
    Check if current user has full access to /dev/uinput.
    
    Returns:
        tuple: (has_access: bool, reason: str)
            - has_access: True if user can use uinput for keystroke injection
            - reason: Human-readable explanation of the status
    """
    # Check if device exists
    if not check_uinput_exists():
        return (False, "The /dev/uinput device does not exist. "
                       "The uinput kernel module may not be loaded.")
    
    # Check read access
    if not check_uinput_readable():
        return (False, "Cannot read /dev/uinput. "
                       "You need permission to access this device for typing.")
    
    # Check write access
    if not check_uinput_writable():
        return (False, "Cannot write to /dev/uinput. "
                       "You need write permission for keystroke injection.")
    
    return (True, "You have full access to /dev/uinput. Typing should work.")


def _readable_input_devices():
    """Input device nodes this user can actually open, asked evdev's way.

    evdev's list_devices() keeps only nodes passing os.access(R_OK | W_OK) and
    returns an empty list rather than raising, so posing the question exactly as
    evdev poses it is the only answer that predicts whether hotkeys will work.

    Group membership is deliberately not used as a proxy here: a user can be in
    'input' while the nodes carry the wrong mode, and an ACL can grant access
    with no group at all. Ask about the capability, not about the mechanism.
    """
    try:
        from evdev import list_devices
        return list(list_devices())
    except Exception:
        import glob
        return [p for p in glob.glob("/dev/input/event*")
                if os.access(p, os.R_OK | os.W_OK)]


def check_input_read_permission():
    """
    Check whether TuxTalk can read hotkeys from /dev/input.

    Returns:
        tuple: (has_access: bool, reason: str)
    """
    if _readable_input_devices():
        return (True, "You can read input devices. Hotkeys should work.")
    return (False, "Cannot read any keyboard under /dev/input, so hotkeys "
                   "cannot work. This usually means you are not in the "
                   "'input' group.")


def check_all_device_permissions():
    """
    Check BOTH device permissions TuxTalk needs, not just one.

    Typing keystrokes needs /dev/uinput; reading hotkeys needs /dev/input.
    They are granted by different mechanisms — logind hands out a per-user ACL
    on /dev/uinput, while /dev/input relies on 'input' group membership — so on
    some distributions (Fedora) one works while the other does not.

    Gating setup on the uinput check alone meant Fedora users had setup skipped
    entirely, and with it the `usermod -a -G input` that grants hotkey access.
    They could type, but no hotkey could ever be read.

    Returns:
        tuple: (has_access: bool, reason: str)
    """
    ok_uinput, uinput_reason = check_uinput_permission()
    ok_input, input_reason = check_input_read_permission()

    if ok_uinput and ok_input:
        return (True, "Typing and hotkeys both have the access they need.")
    if not ok_uinput and not ok_input:
        return (False, f"{uinput_reason} Also: {input_reason}")
    return (False, uinput_reason if not ok_uinput else input_reason)


def reboot_system() -> bool:
    """Reboot the machine via systemd-logind.

    `systemctl reboot` asks logind, which lets an active local desktop session
    reboot without a password. Returns False rather than raising if the command
    is missing or refused, so the caller can fall back to telling the user to
    restart manually.
    """
    try:
        result = subprocess.run(
            ['systemctl', 'reboot'],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 and result.stderr:
            logger.warning(f"systemctl reboot refused: {result.stderr.strip()}")
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning(f"Could not reboot: {e}")
        return False


def check_user_in_input_group():
    """
    Check if current user is in the 'input' group.
    
    Returns:
        bool: True if user is in 'input' group, False otherwise
    """
    try:
        username = os.getlogin()
    except OSError:
        # Fallback for some environments
        username = os.environ.get('USER', '')
    
    if not username:
        return False
    
    try:
        input_group = grp.getgrnam('input')
        in_group = username in input_group.gr_mem
        logger.debug(f"User '{username}' in 'input' group: {in_group}")
        return in_group
    except KeyError:
        # 'input' group doesn't exist
        logger.debug("'input' group does not exist")
        return False
    except Exception as e:
        logger.warning(f"Error checking input group membership: {e}")
        return False


def check_udev_rule_exists():
    """
    Check if our udev rule is already installed.
    
    Returns:
        bool: True if the rule file exists, False otherwise
    """
    exists = os.path.exists(UDEV_RULE_PATH)
    logger.debug(f"Udev rule exists at {UDEV_RULE_PATH}: {exists}")
    return exists


# ydotoold systemd service template - {ydotoold_path} will be replaced with actual path
YDOTOOLD_SERVICE_TEMPLATE = '''[Unit]
Description=ydotool daemon (TuxTalk keystroke injection)
After=graphical-session.target

[Service]
Environment=XDG_RUNTIME_DIR=%t
ExecStart={ydotoold_path} --socket-path=%t/.ydotool_socket
Restart=on-failure

[Install]
WantedBy=default.target
'''


# The standard system program folders, for lookups that must never find the
# AppImage's bundled copies.
_SYSTEM_PATH = "/usr/sbin:/sbin:/usr/bin:/bin:/usr/local/bin:/usr/local/sbin"


def find_ydotoold_path():
    """
    Find the actual path to ydotoold binary on the SYSTEM (not inside AppImage).

    IMPORTANT: This function ONLY returns system paths, NEVER AppImage paths.
    If ydotoold is not found at a system location, it returns None.

    Returns:
        str or None: Path to ydotoold on SYSTEM, or None if not found
    """
    def is_appimage_path(path):
        """Check if path is inside an AppImage mount point."""
        if not path:
            return False
        # Check common AppImage mount patterns
        path_lower = path.lower()
        return ('/tmp/.mount_' in path or
                '/tmp/appimage' in path_lower or
                '/appimage' in path_lower or
                os.environ.get('APPDIR', '') and os.environ.get('APPDIR', '') in path)

    # Check AppImage environment
    appdir = os.environ.get('APPDIR', '')
    if appdir:
        logger.info(f"Running from AppImage (APPDIR={appdir}) - will only use system ydotoold")

    # Search ONLY the standard system dirs, never the inherited PATH, which
    # inside the AppImage starts with the AppImage's own usr/bin. In-process,
    # so it works where no `which` binary is installed (minimal Arch).
    found_path = shutil.which("ydotoold", path=_SYSTEM_PATH)
    if found_path and not is_appimage_path(found_path):
        logger.info(f"Found system ydotoold: {found_path}")
        return found_path
    if found_path:
        logger.warning(f"Rejecting AppImage path: {found_path}")

    logger.warning("ydotoold not found in any common location")
    return None


def ydotool_socket_path():
    """The socket ydotool talks to ydotoold on: YDOTOOL_SOCKET when set, else
    .ydotool_socket in this user's runtime folder."""
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return os.environ.get("YDOTOOL_SOCKET") or os.path.join(runtime, ".ydotool_socket")


def check_ydotoold_running():
    """Whether this user's ydotoold process is alive. Not its socket file: a
    daemon that died leaves .ydotool_socket behind, and then nothing would
    restart it. Only this user's: another user's, or a system service's,
    listens on a socket this user's ydotool doesn't use."""
    try:
        return subprocess.run(["pgrep", "-u", str(os.getuid()), "-x", "ydotoold"],
                              capture_output=True, timeout=2).returncode == 0
    except Exception as e:
        logger.warning(f"Could not check ydotoold status: {e}")
        return True     # can't tell: don't report it stopped or start a second one


def check_ydotoold_service_exists():
    """
    Check if ydotoold systemd user service is installed.

    Returns:
        bool: True if service file exists, False otherwise
    """
    service_path = os.path.expanduser("~/.config/systemd/user/ydotoold.service")
    return os.path.exists(service_path)


def check_ydotool_available():
    """
    Check whether a usable ydotool binary is on PATH -- bundled copies COUNT.

    Deliberately NOT the same lookup as find_ydotoold_path(). This one searches
    the inherited PATH, so inside the AppImage it finds the bundled
    usr/bin/ydotool (AppRun puts that directory first) and correctly reports it
    as available. That is the answer every caller here wants: "can we type?"

    find_ydotoold_path() sanitises PATH and rejects AppImage paths instead,
    because it feeds a systemd user unit that cannot reference a mount point
    which disappears when the app exits.

    Do NOT "fix" this to match find_ydotoold_path(). Doing so would show
    "ydotool not installed (required)" on the welcome screen to every AppImage
    user who already has a working bundled copy, and would make
    install_ydotool_with_pkexec() prompt to install a package that is already
    present. tests/test_ydotool_discovery.py guards both halves.

    Returns:
        tuple: (available: bool, path: str or None)
    """
    path = shutil.which("ydotool")
    return (True, path) if path else (False, None)


def setup_ydotoold_service():
    """
    Set up the ydotoold systemd user service.
    Creates the service file and enables/starts it.

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        # Check if ydotool is installed system-wide
        ydotool_installed, _ = check_ydotool_available()

        if not ydotool_installed:
            return (False, "ydotool is not installed. Please install it first:\n"
                          "  Ubuntu/Debian: sudo apt install ydotool\n"
                          "  Fedora: sudo dnf install ydotool\n"
                          "  Arch: sudo pacman -S ydotool")

        # Find ydotoold binary path (it's the daemon, not the CLI tool)
        ydotoold_path = find_ydotoold_path()
        if not ydotoold_path:
            # No system ydotoold, but TuxTalk's own copy is on PATH. A systemd
            # unit can't point at the AppImage's mount, which goes away when
            # the app exits, so the tray starts this copy itself instead.
            if shutil.which("ydotoold"):
                ensure_ydotoold_running()
                return (True, "Using TuxTalk's built-in typing helper; it starts with TuxTalk")
            return (False, "ydotoold daemon not found. The ydotool package may be incomplete.\n"
                          "Try reinstalling: sudo apt install --reinstall ydotool")

        logger.info(f"Found ydotoold at: {ydotoold_path}")

        # Create systemd user directory if it doesn't exist
        systemd_user_dir = os.path.expanduser("~/.config/systemd/user")
        os.makedirs(systemd_user_dir, exist_ok=True)

        # Write the service file with the actual ydotoold path
        service_path = os.path.join(systemd_user_dir, "ydotoold.service")
        service_content = YDOTOOLD_SERVICE_TEMPLATE.format(ydotoold_path=ydotoold_path)
        with open(service_path, 'w') as f:
            f.write(service_content)

        logger.info(f"Created ydotoold service at {service_path}")

        # Reload systemd user daemon
        subprocess.run(['systemctl', '--user', 'daemon-reload'],
                      capture_output=True, timeout=10)

        # Enable the service
        result = subprocess.run(['systemctl', '--user', 'enable', 'ydotoold.service'],
                               capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            logger.warning(f"Failed to enable ydotoold: {result.stderr}")

        # Start the service
        result = subprocess.run(['systemctl', '--user', 'start', 'ydotoold.service'],
                               capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            logger.error(f"systemctl start failed: {result.stderr}")
            return (False, f"Failed to start ydotoold service: {result.stderr}")

        # Verify it's running (with retries - service may take a moment to create socket)
        import time
        for attempt in range(5):
            time.sleep(0.5)  # Wait 0.5s between checks (total up to 2.5s)
            if check_ydotoold_running():
                logger.info(f"ydotoold running after {attempt + 1} check(s)")
                return (True, "ydotoold service set up and running successfully!")
            logger.debug(f"ydotoold check attempt {attempt + 1} failed, retrying...")
        else:
            # Get detailed status for debugging
            status_result = subprocess.run(
                ['systemctl', '--user', 'status', 'ydotoold.service'],
                capture_output=True, text=True, timeout=10
            )
            logger.error(f"ydotoold service status:\n{status_result.stdout}\n{status_result.stderr}")

            # Also check journal for errors
            journal_result = subprocess.run(
                ['journalctl', '--user', '-u', 'ydotoold.service', '-n', '10', '--no-pager'],
                capture_output=True, text=True, timeout=10
            )
            logger.error(f"ydotoold journal:\n{journal_result.stdout}")

            return (False, f"Service was set up but failed to start. "
                          f"Check: systemctl --user status ydotoold\n"
                          f"Service file uses: {ydotoold_path}")

    except Exception as e:
        logger.error(f"Error setting up ydotoold service: {e}")
        return (False, f"Error setting up ydotoold: {e}")


def ensure_ydotoold_running():
    """Start ydotoold if it isn't running; never raises or waits. Called at
    tray launch and again after Fix Typing, since a daemon that started
    without permission to /dev/uinput has already exited."""
    # The Flatpak types through libei, not ydotool, and doesn't ship the daemon.
    if os.environ.get("FLATPAK_ID"):
        return
    try:
        if check_ydotoold_running():
            logger.debug("ydotoold is already running")
            return
        logger.info("Starting ydotoold daemon for text injection...")
        # The socket named explicitly, so the daemon listens where ydotool
        # looks even when XDG_RUNTIME_DIR is unset (ydotoold then uses /tmp).
        subprocess.Popen(["ydotoold", f"--socket-path={ydotool_socket_path()}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info("ydotoold launch requested")
    except FileNotFoundError:
        logger.warning("ydotoold not found in PATH - text injection may not work")
    except Exception as e:
        logger.error(f"Failed to start ydotoold: {e}")


# Why a dictation couldn't be typed, for the "didn't reach the window" notice.
TYPING_RESTART_PENDING = ("TuxTalk can't type yet: restart your computer to finish "
                          "the typing setup.")
TYPING_NO_PERMISSION = ("TuxTalk doesn't have permission to type. Open Preferences, "
                        "Advanced, Fix Typing Permissions, then restart your computer.")
TYPING_HELPER_STOPPED = ("TuxTalk's typing helper had stopped. It's been started "
                         "again, so try that dictation once more.")


def _username():
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        return os.environ.get("USER", "")


def _input_group_pending_restart():
    """True when setup has added this user to 'input' but the login session
    predates it. os.getgroups() is fixed at login; the group's member list
    changes the moment usermod runs."""
    try:
        group = grp.getgrnam("input")
    except KeyError:
        return False
    return _username() in group.gr_mem and group.gr_gid not in os.getgroups()


def typing_blocked_reason():
    """Why ydotool can't type right now, as advice for the user, or None
    (also when there's nothing to check: the Flatpak, or no /dev/uinput)."""
    if os.environ.get("FLATPAK_ID") or not os.path.exists("/dev/uinput"):
        return None
    if not check_uinput_writable():
        if _input_group_pending_restart():
            return TYPING_RESTART_PENDING
        return TYPING_NO_PERMISSION
    if not check_ydotoold_running():
        return TYPING_HELPER_STOPPED
    return None


def get_ydotoold_status():
    """
    Get comprehensive status of ydotoold.

    Returns:
        dict: Status information with keys:
            - running: bool
            - service_exists: bool
            - ydotool_installed: bool
            - needs_setup: bool
            - message: str
    """
    running = check_ydotoold_running()
    service_exists = check_ydotoold_service_exists()
    ydotool_installed, _ = check_ydotool_available()

    if running:
        return {
            'running': True,
            'service_exists': service_exists,
            'ydotool_installed': ydotool_installed,
            'needs_setup': False,
            'message': "ydotoold is running - keystroke injection ready"
        }

    if not ydotool_installed:
        return {
            'running': False,
            'service_exists': service_exists,
            'ydotool_installed': False,
            'needs_setup': True,
            'message': "ydotool is not installed on this system"
        }

    if not service_exists:
        return {
            'running': False,
            'service_exists': False,
            'ydotool_installed': True,
            'needs_setup': True,
            'message': "ydotoold service needs to be set up"
        }

    # Service exists but not running
    return {
        'running': False,
        'service_exists': True,
        'ydotool_installed': True,
        'needs_setup': True,
        'message': "ydotoold service exists but is not running"
    }


def detect_package_manager():
    """
    Detect which package manager is available on the system.

    Returns:
        tuple: (package_manager: str, install_command: list) or (None, None) if not detected
    """
    import shutil

    # Check for package managers in order of preference
    package_managers = [
        ('dnf', ['dnf', 'install', '-y', 'ydotool']),      # Fedora, RHEL, CentOS
        ('apt', ['apt', 'install', '-y', 'ydotool']),      # Debian, Ubuntu
        ('pacman', ['pacman', '-S', '--noconfirm', 'ydotool']),  # Arch, Manjaro
        ('zypper', ['zypper', 'install', '-y', 'ydotool']),  # openSUSE
        ('apk', ['apk', 'add', 'ydotool']),                # Alpine
    ]

    for pm_name, install_cmd in package_managers:
        if shutil.which(pm_name):
            logger.debug(f"Detected package manager: {pm_name}")
            return (pm_name, install_cmd)

    logger.warning("No supported package manager detected")
    return (None, None)


# =============================================================================
# PortAudio Detection and Installation
# =============================================================================

def check_portaudio_installed():
    """
    Check if PortAudio library is installed on the system.
    PortAudio is required by sounddevice for audio recording.

    Returns:
        tuple: (installed: bool, message: str)
    """
    import ctypes.util

    # Try to find libportaudio
    portaudio_lib = ctypes.util.find_library('portaudio')

    if portaudio_lib:
        logger.debug(f"PortAudio found: {portaudio_lib}")
        return (True, f"PortAudio library found: {portaudio_lib}")

    # Fallback: Try common library paths directly
    common_paths = [
        '/usr/lib/libportaudio.so.2',
        '/usr/lib64/libportaudio.so.2',
        '/usr/lib/x86_64-linux-gnu/libportaudio.so.2',
        '/usr/lib/aarch64-linux-gnu/libportaudio.so.2',
    ]

    for path in common_paths:
        if os.path.exists(path):
            logger.debug(f"PortAudio found at: {path}")
            return (True, f"PortAudio library found: {path}")

    logger.warning("PortAudio library not found")
    return (False, "PortAudio library not found. Audio recording requires libportaudio.")


def get_portaudio_install_command():
    """
    Get the package manager command to install PortAudio.

    Returns:
        tuple: (package_manager: str, install_command: list) or (None, None) if not detected
    """
    import shutil

    # Package names differ by distro
    # Ubuntu/Debian: libportaudio2
    # Fedora/RHEL: portaudio
    # Arch: portaudio
    # openSUSE: portaudio
    package_managers = [
        ('dnf', ['dnf', 'install', '-y', 'portaudio']),           # Fedora, RHEL, CentOS
        ('apt', ['apt', 'install', '-y', 'libportaudio2']),       # Debian, Ubuntu
        ('pacman', ['pacman', '-S', '--noconfirm', 'portaudio']), # Arch, Manjaro
        ('zypper', ['zypper', 'install', '-y', 'portaudio']),     # openSUSE
        ('apk', ['apk', 'add', 'portaudio']),                     # Alpine
    ]

    for pm_name, install_cmd in package_managers:
        if shutil.which(pm_name):
            logger.debug(f"PortAudio install command for {pm_name}: {install_cmd}")
            return (pm_name, install_cmd)

    logger.warning("No supported package manager detected for PortAudio")
    return (None, None)


def install_portaudio_with_pkexec():
    """
    Install PortAudio using the system package manager with pkexec for privilege escalation.

    Returns:
        tuple: (success: bool, message: str)
    """
    # Check if already installed
    installed, _ = check_portaudio_installed()
    if installed:
        return (True, "PortAudio is already installed!")

    # Detect package manager and get install command
    pm_name, install_cmd = get_portaudio_install_command()

    if not pm_name:
        return (False, "Could not detect your package manager.\n"
                      "Please install PortAudio manually:\n"
                      "  Ubuntu/Debian: sudo apt install libportaudio2\n"
                      "  Fedora: sudo dnf install portaudio\n"
                      "  Arch: sudo pacman -S portaudio")

    logger.info(f"Installing PortAudio using {pm_name}...")

    try:
        # Run the install command with pkexec
        full_cmd = ['pkexec'] + install_cmd
        logger.info(f"Running: {' '.join(full_cmd)}")

        result = subprocess.run(full_cmd, capture_output=True, text=True,
                                timeout=PKEXEC_INSTALL_TIMEOUT)

        if result.returncode == 0:
            # Verify installation
            installed, _ = check_portaudio_installed()
            if installed:
                logger.info("PortAudio installed successfully")
                return (True, "PortAudio installed successfully!")
            else:
                return (False, "Installation appeared to succeed but PortAudio not found. "
                              "You may need to restart TuxTalk.")
        elif result.returncode == 126:
            # User cancelled authentication
            logger.info("User cancelled pkexec authentication for PortAudio install")
            return (False, "Installation was cancelled.")
        else:
            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.error(f"Failed to install PortAudio: {error_msg}")
            return (False, f"Installation failed:\n{error_msg}")

    except subprocess.TimeoutExpired:
        logger.error("PortAudio installation timed out")
        return (False, "Installation timed out. Please try again or install manually.")
    except FileNotFoundError:
        logger.error("pkexec not found")
        return (False, "pkexec not found. Please install polkit or install PortAudio manually.")
    except Exception as e:
        logger.error(f"Error installing PortAudio: {e}")
        return (False, f"Error: {e}")


def get_portaudio_status():
    """
    Get comprehensive status of PortAudio installation.

    Returns:
        dict: Status information with keys:
            - installed: bool
            - needs_install: bool
            - message: str
    """
    installed, _ = check_portaudio_installed()

    if installed:
        return {
            'installed': True,
            'needs_install': False,
            'message': "PortAudio is installed - audio recording ready"
        }

    return {
        'installed': False,
        'needs_install': True,
        'message': "PortAudio not installed - required for audio recording"
    }


def install_ydotool_with_pkexec():
    """
    Install ydotool using the system package manager with pkexec for privilege escalation.

    Returns:
        tuple: (success: bool, message: str)
    """
    # Check if already installed
    installed, _ = check_ydotool_available()
    if installed:
        return (True, "ydotool is already installed!")

    # Detect package manager
    pm_name, install_cmd = detect_package_manager()

    if not pm_name:
        return (False, "Could not detect your package manager.\n"
                      "Please install ydotool manually:\n"
                      "  Ubuntu/Debian: sudo apt install ydotool\n"
                      "  Fedora: sudo dnf install ydotool\n"
                      "  Arch: sudo pacman -S ydotool")

    logger.info(f"Installing ydotool using {pm_name}...")

    try:
        # Run the install command with pkexec
        full_cmd = ['pkexec'] + install_cmd
        logger.info(f"Running: {' '.join(full_cmd)}")

        result = subprocess.run(full_cmd, capture_output=True, text=True,
                                timeout=PKEXEC_INSTALL_TIMEOUT)

        if result.returncode == 0:
            # Verify installation
            installed, path = check_ydotool_available()
            if installed:
                logger.info(f"ydotool installed successfully at {path}")
                return (True, "ydotool installed successfully!")
            else:
                return (False, "Installation appeared to succeed but ydotool not found. "
                              "You may need to restart your terminal or log out and back in.")
        elif result.returncode == 126:
            # User cancelled authentication
            logger.info("User cancelled pkexec authentication for ydotool install")
            return (False, "Installation was cancelled.")
        else:
            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.error(f"Failed to install ydotool: {error_msg}")
            return (False, f"Installation failed:\n{error_msg}")

    except subprocess.TimeoutExpired:
        logger.error("ydotool installation timed out")
        return (False, "Installation timed out. Please try again or install manually.")
    except FileNotFoundError:
        logger.error("pkexec not found")
        return (False, "pkexec not found. Please install polkit or install ydotool manually.")
    except Exception as e:
        logger.error(f"Error installing ydotool: {e}")
        return (False, f"Error: {e}")


def get_fix_script_content():
    """
    Get the shell script content that fixes uinput permissions.
    This script is run with pkexec (admin privileges).
    
    Returns:
        str: Shell script content
    """
    # Resolve the username from the passwd database (canonical — can't be
    # spoofed via the USER env var) and shell-quote it. This script runs as
    # ROOT via pkexec, so an unquoted/attacker-controlled username would be a
    # root shell-injection vector.
    try:
        username = pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        username = os.environ.get('USER', '')
    quoted_user = shlex.quote(username)

    return f'''#!/bin/bash
# TuxTalk uinput permission fix script
# This script is run with administrator privileges via pkexec

set -e

# Username resolved and shell-quoted by TuxTalk; used only via "$TUXTALK_USER"
TUXTALK_USER={quoted_user}

echo "Setting up uinput access for TuxTalk..."

# Create the udev rule
cat > {UDEV_RULE_PATH} << 'RULE'
{UDEV_RULE_CONTENT}RULE

echo "Created udev rule at {UDEV_RULE_PATH}"

# Add user to the input group (does nothing when already a member)
usermod -a -G input "$TUXTALK_USER"
echo "$TUXTALK_USER is in the input group"

# Reload udev rules and apply them to /dev/uinput only, not every device
udevadm control --reload-rules
udevadm trigger --sysname-match=uinput

echo ""
echo "Success! Uinput permissions configured."
echo ""
echo "IMPORTANT: Restart the computer to apply the group changes."
echo "(Logging out and back in is often not enough — a lingering user"
echo " session keeps the old group list alive.)"
'''


# How long a pkexec step may take. It includes the time the user spends at
# the password dialog, and for an install the package download too.
PKEXEC_SCRIPT_TIMEOUT = 300
PKEXEC_INSTALL_TIMEOUT = 900


def install_udev_rule_with_pkexec():
    """
    Install the udev rule using pkexec for privilege escalation.

    Returns:
        tuple: (success: bool, message: str)
    """
    import tempfile

    # Create temporary script
    script_content = get_fix_script_content()
    script_path = None

    try:
        # The script runs as root through `bash script_path`, so it needs no
        # execute bit and stays readable by this user only (mkstemp's 0600).
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write(script_content)
            script_path = f.name

        logger.info(f"Running udev fix script with pkexec: {script_path}")
        result = subprocess.run(['pkexec', 'bash', script_path],
                              capture_output=True, text=True, timeout=PKEXEC_SCRIPT_TIMEOUT)

        if result.returncode == 0:
            logger.info("Udev rule installed successfully")
            return (True, "Permissions configured successfully!\n\n"
                         "Restart your computer to apply (logging out is often not enough).")
        elif result.returncode == 126:
            # User cancelled the authentication dialog
            logger.info("User cancelled pkexec authentication")
            return (False, "Authentication was cancelled.")
        else:
            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.error(f"Failed to install udev rule: {error_msg}")
            return (False, f"Failed to configure permissions:\n{error_msg}")
            
    except subprocess.TimeoutExpired:
        logger.error("pkexec timed out")
        return (False, "The operation timed out. Please try again.")
    except FileNotFoundError:
        logger.error("pkexec not found")
        return (False, "pkexec not found. Please install polkit to use this feature.")
    except Exception as e:
        logger.error(f"Error running pkexec: {e}")
        return (False, f"Error: {e}")
    finally:
        # Removed on every path, a timeout included, so no root script is
        # left behind in /tmp.
        if script_path:
            try:
                os.unlink(script_path)
            except OSError:
                pass

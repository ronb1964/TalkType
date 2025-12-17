#!/usr/bin/env python3
"""
uinput Helper Module for TalkType

Handles detection and fixing of /dev/uinput permissions required for
keystroke injection via ydotool on Wayland.

The problem:
- ydotool uses the Linux uinput subsystem to inject keystrokes
- /dev/uinput requires special permissions (usually root or uinput group)
- Without access, typing injection silently fails

The solution:
- Detect if user can access /dev/uinput
- If not, offer to install a udev rule that grants access
- The udev rule adds the user to the appropriate group or sets ACLs
"""

import os
import subprocess
import grp
from .logger import setup_logger

logger = setup_logger(__name__)

# The udev rule content that grants access to /dev/uinput
# This creates a new 'uinput' group and gives it read/write access
UDEV_RULE_CONTENT = '''# TalkType: Allow users in the 'input' group to access uinput
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


def test_ydotool_works():
    """
    Actually test if ydotool can inject keystrokes.
    This is the most reliable check as it tests the full stack.
    
    Returns:
        tuple: (works: bool, reason: str)
    """
    # First check if ydotool is available
    ydotool_path = None
    
    # Check in PATH
    for path in os.environ.get('PATH', '').split(':'):
        candidate = os.path.join(path, 'ydotool')
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            ydotool_path = candidate
            break
    
    if not ydotool_path:
        # Check bundled location (AppImage)
        appdir = os.environ.get('APPDIR', '')
        if appdir:
            candidate = os.path.join(appdir, 'usr', 'bin', 'ydotool')
            if os.path.isfile(candidate):
                ydotool_path = candidate
    
    if not ydotool_path:
        return (False, "ydotool not found. It should be bundled with TalkType.")
    
    # Check if ydotoold is running
    try:
        result = subprocess.run(['pgrep', '-f', 'ydotoold'], 
                              capture_output=True, timeout=2)
        if result.returncode != 0:
            return (False, "ydotoold daemon is not running. "
                          "TalkType should start it automatically.")
    except Exception as e:
        logger.warning(f"Could not check ydotoold status: {e}")
    
    # The actual typing test would require ydotoold to be running
    # and would inject real keystrokes - too intrusive for a check
    # So we just verify uinput access
    has_access, reason = check_uinput_permission()
    
    if has_access:
        return (True, "ydotool and /dev/uinput are ready for keystroke injection.")
    else:
        return (False, reason)


# ydotoold systemd service content
YDOTOOLD_SERVICE_CONTENT = '''[Unit]
Description=ydotool daemon (TalkType keystroke injection)
After=graphical-session.target

[Service]
Environment=XDG_RUNTIME_DIR=%t
ExecStart=/usr/bin/ydotoold --socket-path=%t/.ydotool_socket
Restart=on-failure

[Install]
WantedBy=default.target
'''


def check_ydotoold_running():
    """
    Check if ydotoold daemon is currently running.

    Returns:
        bool: True if ydotoold is running, False otherwise
    """
    try:
        result = subprocess.run(['pgrep', '-f', 'ydotoold'],
                               capture_output=True, timeout=2)
        return result.returncode == 0
    except Exception as e:
        logger.warning(f"Could not check ydotoold status: {e}")
        return False


def check_ydotoold_service_exists():
    """
    Check if ydotoold systemd user service is installed.

    Returns:
        bool: True if service file exists, False otherwise
    """
    service_path = os.path.expanduser("~/.config/systemd/user/ydotoold.service")
    return os.path.exists(service_path)


def check_system_ydotool_installed():
    """
    Check if ydotool is installed system-wide.

    Returns:
        tuple: (installed: bool, path: str or None)
    """
    try:
        result = subprocess.run(['which', 'ydotool'],
                               capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            return (True, result.stdout.strip())
        return (False, None)
    except Exception:
        return (False, None)


def setup_ydotoold_service():
    """
    Set up the ydotoold systemd user service.
    Creates the service file and enables/starts it.

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        # Check if ydotool is installed system-wide
        ydotool_installed, ydotool_path = check_system_ydotool_installed()

        if not ydotool_installed:
            return (False, "ydotool is not installed. Please install it first:\n"
                          "  Ubuntu/Debian: sudo apt install ydotool\n"
                          "  Fedora: sudo dnf install ydotool\n"
                          "  Arch: sudo pacman -S ydotool")

        # Create systemd user directory if it doesn't exist
        systemd_user_dir = os.path.expanduser("~/.config/systemd/user")
        os.makedirs(systemd_user_dir, exist_ok=True)

        # Write the service file
        service_path = os.path.join(systemd_user_dir, "ydotoold.service")
        with open(service_path, 'w') as f:
            f.write(YDOTOOLD_SERVICE_CONTENT)

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
            return (False, f"Failed to start ydotoold service: {result.stderr}")

        # Verify it's running
        import time
        time.sleep(0.5)  # Give it a moment to start

        if check_ydotoold_running():
            return (True, "ydotoold service set up and running successfully!")
        else:
            return (False, "Service was set up but failed to start. "
                          "Check: systemctl --user status ydotoold")

    except Exception as e:
        logger.error(f"Error setting up ydotoold service: {e}")
        return (False, f"Error setting up ydotoold: {e}")


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
    ydotool_installed, _ = check_system_ydotool_installed()

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


def install_ydotool_with_pkexec(parent_window=None):
    """
    Install ydotool using the system package manager with pkexec for privilege escalation.

    Args:
        parent_window: Optional GTK parent window for the pkexec dialog

    Returns:
        tuple: (success: bool, message: str)
    """
    import subprocess

    # Check if already installed
    installed, _ = check_system_ydotool_installed()
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

        result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=300)

        if result.returncode == 0:
            # Verify installation
            installed, path = check_system_ydotool_installed()
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
    username = os.environ.get('USER', '')
    
    return f'''#!/bin/bash
# TalkType uinput permission fix script
# This script is run with administrator privileges via pkexec

set -e

echo "Setting up uinput access for TalkType..."

# Create the udev rule
cat > {UDEV_RULE_PATH} << 'RULE'
{UDEV_RULE_CONTENT}RULE

echo "Created udev rule at {UDEV_RULE_PATH}"

# Add user to input group if not already
if ! groups {username} | grep -q '\\binput\\b'; then
    usermod -a -G input {username}
    echo "Added {username} to input group"
else
    echo "{username} is already in input group"
fi

# Reload udev rules
udevadm control --reload-rules
udevadm trigger

echo ""
echo "Success! Uinput permissions configured."
echo ""
echo "IMPORTANT: Log out and back in to apply the group changes."
echo "(Some systems may require a full reboot instead.)"
'''


def install_udev_rule_with_pkexec(parent_window=None):
    """
    Install the udev rule using pkexec for privilege escalation.
    
    Args:
        parent_window: Optional GTK parent window for the pkexec dialog
        
    Returns:
        tuple: (success: bool, message: str)
    """
    import tempfile
    import stat
    
    # Create temporary script
    script_content = get_fix_script_content()
    
    try:
        # Write script to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write(script_content)
            script_path = f.name
        
        # Make executable
        os.chmod(script_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP)
        
        # Run with pkexec
        logger.info(f"Running udev fix script with pkexec: {script_path}")
        result = subprocess.run(['pkexec', 'bash', script_path],
                              capture_output=True, text=True, timeout=60)
        
        # Clean up temp file
        try:
            os.unlink(script_path)
        except:
            pass
        
        if result.returncode == 0:
            logger.info("Udev rule installed successfully")
            return (True, "Permissions configured successfully!\n\n"
                         "Log out and back in to apply (some systems require reboot).")
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


def show_uinput_fix_dialog(parent=None):
    """
    Show a GTK dialog explaining the uinput permission issue and offering to fix it.
    
    Args:
        parent: Optional parent GTK window
        
    Returns:
        bool: True if user chose to fix and it succeeded, False otherwise
    """
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk
        
        # Check current status
        has_access, reason = check_uinput_permission()
        
        if has_access:
            # Already working, nothing to do
            dialog = Gtk.MessageDialog(
                transient_for=parent,
                modal=True,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="Typing is Ready!"
            )
            dialog.format_secondary_text(
                "Your system is already configured correctly.\n\n"
                "Keystroke injection should work without issues."
            )
            dialog.run()
            dialog.destroy()
            return True
        
        # Show fix dialog
        dialog = Gtk.MessageDialog(
            transient_for=parent,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text="Typing Permission Required"
        )
        
        dialog.format_secondary_markup(
            f"<b>Issue:</b> {reason}\n\n"
            "<b>What this means:</b>\n"
            "TalkType uses the Linux input system to type text into applications. "
            "This requires permission to access /dev/uinput.\n\n"
            "<b>The fix:</b>\n"
            "We'll add a system rule that grants your user account access to the "
            "input device. This is a one-time setup that requires your admin password.\n\n"
            "<b>After the fix:</b>\n"
            "Log out and back in to apply (some systems may require a reboot)."
        )
        
        dialog.add_button("Use Clipboard Instead", Gtk.ResponseType.CANCEL)
        dialog.add_button("Fix Typing (Recommended)", Gtk.ResponseType.OK)
        
        # Style the recommended button
        fix_button = dialog.get_widget_for_response(Gtk.ResponseType.OK)
        if fix_button:
            fix_button.get_style_context().add_class("suggested-action")
        
        response = dialog.run()
        dialog.destroy()
        
        if response == Gtk.ResponseType.OK:
            # User wants to fix
            success, message = install_udev_rule_with_pkexec(parent)
            
            # Show result
            result_dialog = Gtk.MessageDialog(
                transient_for=parent,
                modal=True,
                message_type=Gtk.MessageType.INFO if success else Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Setup Complete" if success else "Setup Failed"
            )
            result_dialog.format_secondary_text(message)
            result_dialog.run()
            result_dialog.destroy()
            
            return success
        else:
            # User chose clipboard mode
            logger.info("User chose to use clipboard mode instead of fixing uinput")
            return False
            
    except Exception as e:
        logger.error(f"Error showing uinput fix dialog: {e}")
        return False


def get_typing_status():
    """
    Get a summary of the typing injection status for display in UI.
    
    Returns:
        dict with keys:
            - 'works': bool - whether typing should work
            - 'status': str - short status text
            - 'details': str - detailed explanation
            - 'can_fix': bool - whether we can offer to fix it
    """
    has_access, reason = check_uinput_permission()
    
    if has_access:
        return {
            'works': True,
            'status': 'Ready',
            'details': 'Keystroke injection is configured and ready.',
            'can_fix': False
        }
    
    # Check if it's fixable
    can_fix = check_uinput_exists()  # If device exists, we can potentially fix permissions
    
    return {
        'works': False,
        'status': 'Permission needed',
        'details': reason,
        'can_fix': can_fix
    }


if __name__ == "__main__":
    # Test the module
    print("Testing uinput Helper Module")
    print("=" * 50)
    
    print(f"\n/dev/uinput exists: {check_uinput_exists()}")
    print(f"Readable: {check_uinput_readable()}")
    print(f"Writable: {check_uinput_writable()}")
    
    has_access, reason = check_uinput_permission()
    print(f"\nHas access: {has_access}")
    print(f"Reason: {reason}")
    
    print(f"\nUser in 'input' group: {check_user_in_input_group()}")
    print(f"Udev rule exists: {check_udev_rule_exists()}")
    
    status = get_typing_status()
    print(f"\nTyping status: {status}")



















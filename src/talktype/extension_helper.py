#!/usr/bin/env python3
"""
GNOME Extension installer for TalkType
"""

import os
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional, Callable

from . import desktop_detect


EXTENSION_UUID = 'talktype@ronb1964.github.io'
EXTENSION_DOWNLOAD_URL = 'https://github.com/ronb1964/TalkType/releases/latest/download/talktype-gnome-extension.zip'


def is_extension_available() -> bool:
    """
    Check if GNOME extension feature is available

    Returns:
        bool: True if running GNOME desktop
    """
    return desktop_detect.is_gnome()


def is_extension_installed() -> bool:
    """Check if TalkType GNOME extension is installed"""
    return desktop_detect.is_extension_installed(EXTENSION_UUID)


def is_extension_enabled() -> bool:
    """Check if TalkType GNOME extension is enabled"""
    return desktop_detect.is_extension_enabled(EXTENSION_UUID)


def get_extension_status() -> dict:
    """
    Get comprehensive extension status

    Returns:
        dict: Status information
    """
    return {
        'available': is_extension_available(),
        'installed': is_extension_installed(),
        'enabled': is_extension_enabled(),
        'gnome_version': desktop_detect.get_gnome_shell_version(),
        'wayland': desktop_detect.is_wayland(),
    }


def install_extension_from_local(source_dir: str, auto_enable: bool = True) -> bool:
    """
    Install extension from local directory

    Args:
        source_dir: Path to extension source directory
        auto_enable: If True, automatically enable the extension after installation

    Returns:
        bool: True if successful
    """
    try:
        ext_dir = desktop_detect.get_extension_dir()
        target_dir = os.path.join(ext_dir, EXTENSION_UUID)

        # Create extensions directory if it doesn't exist
        os.makedirs(ext_dir, exist_ok=True)

        # Remove existing installation
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)

        # Copy extension files
        shutil.copytree(source_dir, target_dir)

        print(f"✅ Extension installed to {target_dir}")

        # Auto-enable if requested
        if auto_enable:
            if enable_extension():
                print("✅ Extension enabled - will be active after logout/login")
            else:
                print("⚠️  Failed to auto-enable extension - you can enable it manually")

        return True

    except Exception as e:
        print(f"❌ Failed to install extension: {e}")
        return False


def get_bundled_extension_path() -> Optional[str]:
    """
    Find the bundled GNOME extension in the AppImage or dev environment.

    Returns:
        str: Path to bundled extension directory, or None if not found
    """
    import sys

    # Possible locations for bundled extension
    possible_paths = []

    # Check if running from AppImage
    appimage_path = os.environ.get('APPIMAGE')
    if appimage_path:
        # AppImage mount point - extension should be in usr/share/gnome-extension/
        appimage_mount = os.path.dirname(sys.executable)
        possible_paths.append(
            os.path.join(appimage_mount, '..', 'share', 'gnome-extension', EXTENSION_UUID)
        )

    # Check squashfs mount point (AppImage internal path)
    if '/tmp/.mount_' in sys.executable or 'squashfs-root' in sys.executable:
        base = os.path.dirname(os.path.dirname(sys.executable))
        possible_paths.append(
            os.path.join(base, 'share', 'gnome-extension', EXTENSION_UUID)
        )

    # Development environment - relative to this file
    this_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(this_dir))
    possible_paths.append(
        os.path.join(project_root, 'gnome-extension', EXTENSION_UUID)
    )

    # Check each path
    for path in possible_paths:
        normalized = os.path.normpath(path)
        metadata_file = os.path.join(normalized, 'metadata.json')
        if os.path.isfile(metadata_file):
            print(f"✅ Found bundled extension at: {normalized}")
            return normalized

    return None


def install_extension(progress_callback: Optional[Callable] = None) -> bool:
    """
    Install GNOME extension from bundled files or download from GitHub.

    Tries to install from bundled files first (AppImage or dev environment),
    falls back to downloading from GitHub releases if bundled files not found.

    Args:
        progress_callback: Optional function(message, percent) for progress updates

    Returns:
        bool: True if successful
    """
    if not is_extension_available():
        if progress_callback:
            progress_callback("GNOME desktop not detected", 0)
        return False

    # First, try to install from bundled files
    bundled_path = get_bundled_extension_path()
    if bundled_path:
        if progress_callback:
            progress_callback("Installing bundled extension...", 50)

        if install_extension_from_local(bundled_path):
            if progress_callback:
                progress_callback("Extension installed successfully!", 100)

            # Enable the extension
            if enable_extension():
                print("✅ Extension enabled - will be active after logout/login")
            else:
                print("⚠️  Failed to auto-enable extension - you can enable it manually from Extensions app")

            return True
        else:
            print("⚠️  Failed to install bundled extension, trying download...")

    # Fall back to downloading from GitHub
    return download_and_install_extension(progress_callback)


def download_and_install_extension(progress_callback: Optional[Callable] = None) -> bool:
    """
    Download and install GNOME extension from GitHub release.

    This is the fallback when bundled extension is not available.

    Args:
        progress_callback: Optional function(message, percent) for progress updates

    Returns:
        bool: True if successful
    """
    import tempfile
    import zipfile

    if not is_extension_available():
        if progress_callback:
            progress_callback("GNOME desktop not detected", 0)
        return False

    try:
        # Create temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, 'extension.zip')

            if progress_callback:
                progress_callback("Downloading extension...", 10)

            # Download hook
            def download_progress_hook(block_num, block_size, total_size):
                if progress_callback and total_size > 0:
                    downloaded = block_num * block_size
                    percent = min(90, 10 + int((downloaded / total_size) * 70))
                    progress_callback(f"Downloading... {int((downloaded / total_size) * 100)}%", percent)

            # Download extension zip
            urllib.request.urlretrieve(
                EXTENSION_DOWNLOAD_URL,
                zip_path,
                reporthook=download_progress_hook
            )

            if progress_callback:
                progress_callback("Extracting extension...", 85)

            # Extract zip
            extract_dir = os.path.join(temp_dir, 'extracted')
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # Find extension directory in extracted files
            extension_source = os.path.join(extract_dir, EXTENSION_UUID)
            if not os.path.exists(extension_source):
                # Maybe it's directly in extract_dir
                extension_source = extract_dir

            if progress_callback:
                progress_callback("Installing extension...", 90)

            # Install
            if not install_extension_from_local(extension_source):
                return False

            if progress_callback:
                progress_callback("Extension installed successfully!", 100)

            # Enable the extension after installation
            # This adds it to org.gnome.shell enabled-extensions so it persists across logout/login
            if progress_callback:
                progress_callback("Enabling extension...", 95)

            if enable_extension():
                print("✅ Extension enabled - will be active after logout/login")
            else:
                print("⚠️  Failed to auto-enable extension - you can enable it manually from Extensions app")

            return True

    except Exception as e:
        if progress_callback:
            progress_callback(f"Installation failed: {e}", 0)
        print(f"❌ Failed to download/install extension: {e}")
        return False


def enable_extension() -> bool:
    """
    Enable the TalkType GNOME extension

    Returns:
        bool: True if successful
    """
    return desktop_detect.enable_extension(EXTENSION_UUID)


def uninstall_extension() -> bool:
    """
    Uninstall the TalkType GNOME extension

    Returns:
        bool: True if successful
    """
    try:
        ext_dir = desktop_detect.get_extension_dir()
        target_dir = os.path.join(ext_dir, EXTENSION_UUID)

        if os.path.exists(target_dir):
            # First, disable the extension (removes from gsettings)
            try:
                subprocess.run(
                    ['gnome-extensions', 'disable', EXTENSION_UUID],
                    capture_output=True,
                    timeout=10
                )
            except Exception:
                pass  # Ignore errors - extension might not be recognized

            # Remove the extension files
            shutil.rmtree(target_dir)
            print(f"✅ Extension uninstalled")
            return True
        else:
            print("Extension not installed")
            return False

    except Exception as e:
        print(f"❌ Failed to uninstall extension: {e}")
        return False


def get_installation_instructions() -> str:
    """
    Get instructions for completing extension installation

    Returns:
        str: Installation instructions
    """
    return """
The GNOME Extension has been installed and enabled!

Location:
    ~/.local/share/gnome-shell/extensions/talktype@ronb1964.github.io/

To activate the extension:
    LOG OUT and LOG BACK IN to load the extension

After logging back in:
    • The TalkType icon will appear in your top panel
    • Click it to start/stop dictation service
    • View active model and device mode
    • Access preferences
    • The extension will STAY ENABLED across future logins

Note: The extension communicates with the TalkType Python app via D-Bus.
Make sure the TalkType service is running for full functionality.
""".strip()


def offer_extension_installation_cli() -> bool:
    """
    CLI fallback for extension installation offer

    Returns:
        bool: True if user wants to install
    """
    print("\n" + "="*60)
    print("🎨 GNOME DESKTOP DETECTED!")
    print("="*60)
    print("\nTalkType has a native GNOME Shell extension that provides:")
    print("\n✨ Enhanced Features:")
    print("  🎯 Panel indicator with recording status")
    print("  🔄 Quick model switcher in top panel")
    print("  🎨 Visual recording feedback")
    print("  ⚡ Better integration with GNOME")
    print("  🔔 Native notifications")
    print("\n📦 Download size: ~3KB (tiny!)")
    print("="*60)

    try:
        response = input("\nWould you like to install the GNOME extension? (y/n): ")
        return response.lower().startswith('y')
    except (EOFError, KeyboardInterrupt):
        print("\nSkipping extension installation")
        return False


def offer_extension_installation(show_gui: bool = True) -> bool:
    """
    Offer to install GNOME extension

    Args:
        show_gui: If True, show GUI dialog. If False, use CLI.

    Returns:
        bool: True if user accepted and installation succeeded
    """
    if not is_extension_available():
        return False

    if is_extension_installed():
        # Already installed
        return True

    # Ask user
    if show_gui:
        try:
            from gi.repository import Gtk, GLib

            # Create dialog
            dialog = Gtk.MessageDialog(
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Install GNOME Extension?",
            )
            dialog.format_secondary_markup(
                "<b>TalkType has a native GNOME Shell extension!</b>\n\n"
                "✨ <b>Features:</b>\n"
                "  • Panel indicator with recording status\n"
                "  • Active model and device display (read-only)\n"
                "  • Enables custom recording indicator positioning on Wayland\n"
                "  • Native GNOME integration with service controls\n\n"
                "📦 <b>Size:</b> ~3KB\n\n"
                "Would you like to install it now?"
            )

            response = dialog.run()
            dialog.destroy()

            if response != Gtk.ResponseType.YES:
                return False

            # User said yes - show progress dialog
            progress_dialog = Gtk.MessageDialog(
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.NONE,
                text="Installing Extension...",
            )
            progress_label = Gtk.Label(label="Please wait...")
            progress_dialog.get_content_area().pack_start(progress_label, True, True, 10)
            progress_dialog.show_all()

            success = [False]

            def do_install():
                def progress(msg, percent):
                    GLib.idle_add(lambda: progress_label.set_text(msg))

                success[0] = install_extension(progress)
                GLib.idle_add(progress_dialog.destroy)

            import threading
            thread = threading.Thread(target=do_install)
            thread.start()

            # Wait for completion
            while thread.is_alive():
                Gtk.main_iteration_do(False)

            if success[0]:
                # Show success message
                info = Gtk.MessageDialog(
                    message_type=Gtk.MessageType.INFO,
                    buttons=Gtk.ButtonsType.OK,
                    text="Extension Installed and Enabled!",
                )
                info.format_secondary_markup(
                    "The GNOME Extension has been <b>installed and enabled</b>.\n\n"
                    "<b>To activate it:</b>\n"
                    "  <b>Log out and log back in</b> to load the extension\n\n"
                    "After logging back in:\n"
                    "  • The TalkType icon will appear in your top panel\n"
                    "  • Click it to control the service and see status\n"
                    "  • The extension will <b>stay enabled</b> across logins\n\n"
                    "<b>Note:</b> The extension communicates with TalkType via D-Bus."
                )
                info.run()
                info.destroy()
                return True
            else:
                # Show error
                error = Gtk.MessageDialog(
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Installation Failed",
                )
                error.format_secondary_text(
                    "Failed to install the GNOME extension.\n"
                    "You can try installing it manually from Preferences > Extensions."
                )
                error.run()
                error.destroy()
                return False

        except ImportError:
            # Fall back to CLI
            return offer_extension_installation(show_gui=False)
    else:
        # CLI mode
        if offer_extension_installation_cli():
            return install_extension()
        return False


if __name__ == '__main__':
    # Test
    print("Testing extension helper...")
    status = get_extension_status()

    print(f"\nGNOME Desktop: {status['available']}")
    print(f"GNOME Version: {status['gnome_version']}")
    print(f"Wayland: {status['wayland']}")
    print(f"Extension Installed: {status['installed']}")
    print(f"Extension Enabled: {status['enabled']}")

    if status['available'] and not status['installed']:
        print("\n" + get_installation_instructions())

#!/usr/bin/env python3
"""
Update checker for TalkType

Checks for updates to AppImage and GNOME extension via GitHub API.
"""

import json
import logging
import os
import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Callable, Tuple

logger = logging.getLogger(__name__)

# GitHub API endpoint for latest release
GITHUB_API_URL = "https://api.github.com/repos/ronb1964/TalkType/releases/latest"

# GitHub raw content URL for fetching extension metadata from a specific tag
GITHUB_RAW_URL = "https://raw.githubusercontent.com/ronb1964/TalkType"

# Extension UUID and path
EXTENSION_UUID = "talktype@ronb1964.github.io"

# Download directory for updates
UPDATE_DIR = os.path.expanduser("~/.local/share/TalkType/updates")

# Standard AppImage install location
APPIMAGE_DIR = os.path.expanduser("~/AppImages")
APPIMAGE_NAME = "TalkType.AppImage"
APPIMAGE_PATH = os.path.join(APPIMAGE_DIR, APPIMAGE_NAME)

# Desktop launcher location
DESKTOP_FILE_PATH = os.path.expanduser("~/.local/share/applications/talktype.desktop")


def get_current_version() -> str:
    """
    Get current TalkType version.

    Tries to read from __version__ first, then falls back to pyproject.toml.

    Returns:
        str: Version string like "0.4.0"
    """
    # Try __version__ first (preferred for runtime)
    try:
        from . import __version__
        if __version__:
            return __version__
    except (ImportError, AttributeError):
        pass

    # Fall back to pyproject.toml
    try:
        # Find pyproject.toml - could be in project root or AppImage
        import sys

        # Try relative to this module
        this_dir = Path(__file__).parent
        project_root = this_dir.parent.parent
        pyproject_path = project_root / "pyproject.toml"

        if not pyproject_path.exists():
            # Try AppImage location
            if "/tmp/.mount_" in sys.executable or "squashfs-root" in sys.executable:
                base = Path(sys.executable).parent.parent
                pyproject_path = base / "pyproject.toml"

        if pyproject_path.exists():
            content = pyproject_path.read_text()
            # Parse version = "X.Y.Z" from TOML
            match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
            if match:
                return match.group(1)
    except Exception as e:
        logger.warning(f"Could not read version from pyproject.toml: {e}")

    return "unknown"


def get_extension_version() -> Optional[int]:
    """
    Get installed GNOME extension version.

    Reads version from the installed extension's metadata.json file.

    Returns:
        int: Version number (e.g., 2), or None if not installed
    """
    ext_path = Path.home() / ".local/share/gnome-shell/extensions" / EXTENSION_UUID / "metadata.json"

    if not ext_path.exists():
        return None

    try:
        with open(ext_path, "r") as f:
            metadata = json.load(f)
            return metadata.get("version")
    except Exception as e:
        logger.warning(f"Could not read extension version: {e}")
        return None


def compare_versions(current: str, latest: str) -> bool:
    """
    Compare semantic versions.

    Args:
        current: Current version string (e.g., "0.4.0")
        latest: Latest version string (e.g., "0.5.0")

    Returns:
        bool: True if latest > current
    """
    def parse_version(v: str) -> Tuple[int, ...]:
        """Parse version string to tuple of integers."""
        # Remove 'v' prefix if present
        v = v.lstrip("v")
        # Split on dots and convert to integers
        parts = []
        for part in v.split("."):
            # Handle parts like "0-beta" by taking just the number
            num_match = re.match(r"(\d+)", part)
            if num_match:
                parts.append(int(num_match.group(1)))
            else:
                parts.append(0)
        return tuple(parts)

    try:
        current_tuple = parse_version(current)
        latest_tuple = parse_version(latest)
        return latest_tuple > current_tuple
    except Exception:
        return False


def fetch_extension_version_from_release(tag: str) -> Optional[int]:
    """
    Fetch extension version from GitHub for a specific release tag.

    This allows us to compare the installed extension version with the
    version in the release, to determine if extension reinstall is needed.

    Args:
        tag: Release tag (e.g., "v0.5.0")

    Returns:
        int: Extension version number, or None if fetch failed
    """
    # URL to the extension metadata.json in the repo at the given tag
    metadata_url = f"{GITHUB_RAW_URL}/{tag}/gnome-extension/{EXTENSION_UUID}/metadata.json"

    try:
        request = urllib.request.Request(
            metadata_url,
            headers={"User-Agent": "TalkType-UpdateChecker"}
        )

        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("version")

    except urllib.error.HTTPError as e:
        logger.debug(f"Could not fetch extension metadata for {tag}: {e.code}")
        return None
    except Exception as e:
        logger.debug(f"Error fetching extension version for {tag}: {e}")
        return None


def fetch_release_by_tag(tag: str) -> Optional[dict]:
    """
    Fetch release info for a specific version tag.

    Args:
        tag: Version tag (e.g., "v0.5.1")

    Returns:
        dict: Release info with body (release notes) and html_url, or None if failed
    """
    # Ensure tag has 'v' prefix
    if not tag.startswith("v"):
        tag = f"v{tag}"

    url = f"https://api.github.com/repos/ronb1964/TalkType/releases/tags/{tag}"

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "TalkType-UpdateChecker",
                "Accept": "application/vnd.github.v3+json"
            }
        )

        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            return {
                "tag_name": data.get("tag_name", ""),
                "name": data.get("name", ""),
                "body": data.get("body", ""),
                "html_url": data.get("html_url", ""),
                "published_at": data.get("published_at", ""),
            }

    except urllib.error.HTTPError as e:
        logger.debug(f"Could not fetch release for {tag}: {e.code}")
        return None
    except Exception as e:
        logger.debug(f"Error fetching release {tag}: {e}")
        return None


def get_releases_url() -> str:
    """Get the URL to the GitHub releases page."""
    return "https://github.com/ronb1964/TalkType/releases"


def fetch_latest_release() -> Optional[dict]:
    """
    Fetch latest release info from GitHub API.

    Returns:
        dict: Release info with keys:
            - tag_name: Version tag (e.g., "v0.5.0")
            - body: Release notes markdown
            - html_url: URL to release page
            - assets: List of downloadable assets
            - appimage_url: Direct download URL for AppImage (if found)
            - extension_url: Direct download URL for extension (if found)
        None: If fetch failed
    """
    try:
        # Create request with User-Agent (GitHub requires this)
        request = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                "User-Agent": "TalkType-UpdateChecker",
                "Accept": "application/vnd.github.v3+json"
            }
        )

        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

            # Extract useful info
            result = {
                "tag_name": data.get("tag_name", ""),
                "name": data.get("name", ""),
                "body": data.get("body", ""),
                "html_url": data.get("html_url", ""),
                "published_at": data.get("published_at", ""),
                "assets": data.get("assets", []),
                "appimage_url": None,
                "extension_url": None,
            }

            # Find AppImage and extension URLs in assets
            for asset in result["assets"]:
                name = asset.get("name", "").lower()
                url = asset.get("browser_download_url", "")

                if name.endswith(".appimage"):
                    result["appimage_url"] = url
                    result["appimage_name"] = asset.get("name", "")
                elif "extension" in name and name.endswith(".zip"):
                    result["extension_url"] = url

            return result

    except urllib.error.HTTPError as e:
        if e.code == 403:
            logger.warning("GitHub API rate limit exceeded. Try again later.")
        else:
            logger.warning(f"GitHub API error: {e.code} {e.reason}")
        return None
    except urllib.error.URLError as e:
        logger.warning(f"Network error checking for updates: {e.reason}")
        return None
    except Exception as e:
        logger.warning(f"Error fetching latest release: {e}")
        return None


def check_for_updates() -> dict:
    """
    Check for available updates.

    Main entry point for update checking. Compares current versions
    against latest GitHub release.

    Returns:
        dict: Update status with keys:
            - success: True if check completed successfully
            - error: Error message if failed
            - current_version: Current AppImage version
            - latest_version: Latest available version
            - update_available: True if AppImage update is available
            - extension_current: Current extension version (or None)
            - extension_latest: Latest extension version (parsed from release)
            - extension_update: True if extension update is available
            - release: Full release info dict (if successful)
    """
    result = {
        "success": False,
        "error": None,
        "current_version": get_current_version(),
        "latest_version": None,
        "update_available": False,
        "extension_current": get_extension_version(),
        "extension_latest": None,
        "extension_update": False,
        "release": None,
    }

    # Fetch latest release
    release = fetch_latest_release()
    if not release:
        result["error"] = "Could not connect to GitHub. Check your internet connection."
        return result

    result["release"] = release

    # Parse latest version from tag (strip 'v' prefix)
    tag = release.get("tag_name", "")
    latest_version = tag.lstrip("v") if tag else None
    result["latest_version"] = latest_version

    # Check if AppImage update is available
    if latest_version and result["current_version"] != "unknown":
        result["update_available"] = compare_versions(
            result["current_version"],
            latest_version
        )

    # Check extension update - smart comparison
    # Fetch the extension version from the release to compare with installed version
    tag = release.get("tag_name", "")
    if tag:
        latest_ext_version = fetch_extension_version_from_release(tag)
        result["extension_latest"] = latest_ext_version

        if result["extension_current"] is not None and latest_ext_version is not None:
            # Compare integer versions
            result["extension_update"] = latest_ext_version > result["extension_current"]
        elif result["extension_current"] is None and latest_ext_version is not None:
            # Extension not installed but available in release
            result["extension_update"] = False  # Not an "update", would be new install
        else:
            # Couldn't determine, assume no update needed
            result["extension_update"] = False

    result["success"] = True
    return result


def download_update(
    url: str,
    filename: str,
    progress_callback: Optional[Callable[[str, int], None]] = None
) -> Optional[str]:
    """
    Download an update file with progress tracking.

    Args:
        url: Download URL
        filename: Name for saved file
        progress_callback: Optional function(message, percent) for progress updates

    Returns:
        str: Path to downloaded file, or None if failed
    """
    try:
        # Create update directory
        os.makedirs(UPDATE_DIR, exist_ok=True)
        dest_path = os.path.join(UPDATE_DIR, filename)

        if progress_callback:
            progress_callback("Starting download...", 0)

        # Progress hook for urlretrieve
        def reporthook(block_num, block_size, total_size):
            if progress_callback and total_size > 0:
                downloaded = block_num * block_size
                percent = min(100, int((downloaded / total_size) * 100))

                # Format size for display
                downloaded_mb = downloaded / (1024 * 1024)
                total_mb = total_size / (1024 * 1024)

                progress_callback(
                    f"Downloading... {downloaded_mb:.1f} / {total_mb:.1f} MB",
                    percent
                )

        # Create request with User-Agent
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "TalkType-UpdateChecker"}
        )

        # Download file
        with urllib.request.urlopen(request, timeout=300) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            block_size = 8192

            with open(dest_path, "wb") as f:
                while True:
                    block = response.read(block_size)
                    if not block:
                        break
                    f.write(block)
                    downloaded += len(block)

                    if progress_callback and total_size > 0:
                        percent = min(100, int((downloaded / total_size) * 100))
                        downloaded_mb = downloaded / (1024 * 1024)
                        total_mb = total_size / (1024 * 1024)
                        progress_callback(
                            f"Downloading... {downloaded_mb:.1f} / {total_mb:.1f} MB",
                            percent
                        )

        if progress_callback:
            progress_callback("Download complete!", 100)

        # Make AppImage executable
        if filename.endswith(".AppImage"):
            os.chmod(dest_path, 0o755)

        return dest_path

    except Exception as e:
        logger.error(f"Download failed: {e}")
        if progress_callback:
            progress_callback(f"Download failed: {e}", 0)
        return None


def get_update_directory() -> str:
    """Get the directory where updates are downloaded."""
    return UPDATE_DIR


def open_update_directory():
    """Open the update directory in file manager."""
    import subprocess

    os.makedirs(UPDATE_DIR, exist_ok=True)

    try:
        subprocess.run(["xdg-open", UPDATE_DIR], check=True)
    except Exception as e:
        logger.error(f"Could not open update directory: {e}")


def open_release_page(url: str):
    """Open release page in browser."""
    import subprocess

    try:
        subprocess.run(["xdg-open", url], check=True)
    except Exception as e:
        logger.error(f"Could not open release page: {e}")


def should_check_today(last_check: str) -> bool:
    """
    Determine if we should check for updates (once per day).

    Args:
        last_check: ISO timestamp string of last check, or empty string

    Returns:
        bool: True if we should check (no check today or never checked)
    """
    from datetime import datetime, date

    if not last_check:
        return True

    try:
        # Parse the ISO timestamp
        last_check_time = datetime.fromisoformat(last_check)
        last_check_date = last_check_time.date()
        today = date.today()
        return last_check_date < today
    except (ValueError, TypeError):
        # Invalid timestamp, check anyway
        return True


def get_current_timestamp() -> str:
    """
    Get current time as ISO timestamp string.

    Returns:
        str: Current time in ISO format
    """
    from datetime import datetime
    return datetime.now().isoformat()


def get_appimage_path() -> str:
    """Get the standard AppImage installation path."""
    return APPIMAGE_PATH


def get_appimage_dir() -> str:
    """Get the standard AppImage directory."""
    return APPIMAGE_DIR


def is_running_from_appimage() -> bool:
    """
    Check if currently running from an AppImage.

    Returns:
        bool: True if running from AppImage, False otherwise
    """
    import sys
    # AppImages run from /tmp/.mount_* or use APPIMAGE env var
    appimage_env = os.environ.get("APPIMAGE", "")
    return bool(appimage_env) or "/tmp/.mount_" in sys.executable


def get_running_appimage_path() -> Optional[str]:
    """
    Get the path to the currently running AppImage.

    Returns:
        str: Path to AppImage, or None if not running from AppImage
    """
    return os.environ.get("APPIMAGE")


def install_update_and_restart(
    downloaded_path: str,
    progress_callback: Optional[Callable[[str, int], None]] = None
) -> Tuple[bool, str]:
    """
    Install a downloaded AppImage update and restart the application.

    This function:
    1. Creates the AppImages directory if needed
    2. Copies the downloaded AppImage to ~/AppImages/TalkType.AppImage
    3. Makes it executable
    4. Restarts the application using the new AppImage

    Args:
        downloaded_path: Path to the downloaded AppImage
        progress_callback: Optional function(message, percent) for progress updates

    Returns:
        Tuple[bool, str]: (success, message)
    """
    import shutil
    import stat

    try:
        if progress_callback:
            progress_callback("Installing update...", 50)

        # Ensure AppImages directory exists
        os.makedirs(APPIMAGE_DIR, exist_ok=True)

        # Copy downloaded AppImage to standard location
        if progress_callback:
            progress_callback("Copying to AppImages folder...", 60)

        shutil.copy2(downloaded_path, APPIMAGE_PATH)

        # Make executable
        os.chmod(APPIMAGE_PATH, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

        if progress_callback:
            progress_callback("Update installed!", 80)

        # Clean up the downloaded file from temp location
        try:
            os.remove(downloaded_path)
        except Exception:
            pass  # Not critical if cleanup fails

        # Clean up update directory
        try:
            update_dir = os.path.dirname(downloaded_path)
            if update_dir and os.path.isdir(update_dir):
                shutil.rmtree(update_dir, ignore_errors=True)
        except Exception:
            pass

        if progress_callback:
            progress_callback("Restarting TalkType...", 90)

        logger.info(f"Update installed to {APPIMAGE_PATH}, restarting...")

        # Restart the application using the new AppImage
        # Use os.execv to replace the current process
        os.execv(APPIMAGE_PATH, [APPIMAGE_PATH])

        # Note: If execv succeeds, we never reach here
        return (True, "Update installed and restarting...")

    except Exception as e:
        logger.error(f"Failed to install update: {e}")
        return (False, f"Failed to install update: {e}")


def _refresh_desktop_menu_cache():
    """
    Refresh the desktop menu cache after creating/removing a .desktop file.

    This is especially needed for KDE/Plasma which doesn't auto-refresh.
    Runs silently - failures are logged but don't raise exceptions.
    """
    import subprocess
    import shutil

    # Try KDE's cache refresh (kbuildsycoca5 or kbuildsycoca6)
    for cmd in ['kbuildsycoca6', 'kbuildsycoca5']:
        if shutil.which(cmd):
            try:
                subprocess.run([cmd, '--noincremental'],
                             capture_output=True, timeout=10)
                logger.debug(f"Desktop menu cache refreshed using {cmd}")
                return
            except Exception as e:
                logger.debug(f"Could not run {cmd}: {e}")

    # Try update-desktop-database for other desktops
    if shutil.which('update-desktop-database'):
        try:
            apps_dir = os.path.dirname(DESKTOP_FILE_PATH)
            subprocess.run(['update-desktop-database', apps_dir],
                         capture_output=True, timeout=10)
            logger.debug("Desktop menu cache refreshed using update-desktop-database")
        except Exception as e:
            logger.debug(f"Could not run update-desktop-database: {e}")


def _install_app_icon() -> Optional[str]:
    """
    Install the TalkType icon to the user's icon directory.

    Copies the app icon from the AppImage or source to ~/.local/share/icons/
    so it can be referenced by the desktop launcher.

    Returns:
        str: Icon name to use in .desktop file, or None if installation failed
    """
    import shutil
    import sys

    icon_dest_dir = os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps")
    icon_dest_path = os.path.join(icon_dest_dir, "talktype.png")

    # If icon already installed, just return the name
    if os.path.exists(icon_dest_path):
        return "talktype"

    # Find the source icon
    icon_source = None

    # Try 1: Look in AppImage location
    appimage_path = os.environ.get("APPIMAGE")
    if appimage_path:
        # Icon should be next to the AppImage or inside mounted AppDir
        appdir = os.environ.get("APPDIR", "")
        if appdir:
            possible_paths = [
                os.path.join(appdir, "io.github.ronb1964.TalkType.png"),
                os.path.join(appdir, "talktype.png"),
                os.path.join(appdir, "usr", "share", "icons", "hicolor", "256x256", "apps", "talktype.png"),
            ]
            for p in possible_paths:
                if os.path.exists(p):
                    icon_source = p
                    break

    # Try 2: Look relative to this module (for dev mode)
    if not icon_source:
        module_dir = Path(__file__).parent
        project_root = module_dir.parent.parent
        possible_paths = [
            project_root / "io.github.ronb1964.TalkType.png",
            project_root / "icons" / "TT_square_light.png",
        ]
        for p in possible_paths:
            if p.exists():
                icon_source = str(p)
                break

    if not icon_source:
        logger.debug("Could not find TalkType icon to install")
        return None

    try:
        # Create icon directory
        os.makedirs(icon_dest_dir, exist_ok=True)

        # Copy icon
        shutil.copy2(icon_source, icon_dest_path)
        logger.info(f"Installed TalkType icon to {icon_dest_path}")

        # Update icon cache (for GTK-based desktops)
        import subprocess
        try:
            icons_base = os.path.expanduser("~/.local/share/icons/hicolor")
            subprocess.run(['gtk-update-icon-cache', '-f', '-t', icons_base],
                         capture_output=True, timeout=10)
        except Exception:
            pass  # Not critical

        return "talktype"

    except Exception as e:
        logger.warning(f"Could not install TalkType icon: {e}")
        return None


def create_desktop_launcher() -> Tuple[bool, str]:
    """
    Create a desktop launcher (.desktop file) for TalkType.

    Creates a launcher in ~/.local/share/applications/ that points to
    the standard AppImage location (~/AppImages/TalkType.AppImage).

    Returns:
        Tuple[bool, str]: (success, message)
    """
    try:
        # Ensure applications directory exists
        apps_dir = os.path.dirname(DESKTOP_FILE_PATH)
        os.makedirs(apps_dir, exist_ok=True)

        # Install the TalkType icon and get the icon name to use
        icon_name = _install_app_icon()
        if not icon_name:
            icon_name = "audio-input-microphone"  # Fallback to system icon

        # Get the current version for the comment
        version = get_current_version()

        # Desktop file content
        desktop_content = f"""[Desktop Entry]
Name=TalkType
Comment=AI-powered speech recognition and dictation (v{version})
Exec={APPIMAGE_PATH}
Icon={icon_name}
Type=Application
Categories=Utility;Accessibility;AudioVideo;
Keywords=dictation;speech;voice;transcription;whisper;
StartupNotify=true
Terminal=false
"""

        # Write the desktop file
        with open(DESKTOP_FILE_PATH, "w") as f:
            f.write(desktop_content)

        # Make it executable (not strictly required but good practice)
        os.chmod(DESKTOP_FILE_PATH, 0o755)

        # Refresh desktop menu cache (especially needed for KDE/Plasma)
        _refresh_desktop_menu_cache()

        logger.info(f"Desktop launcher created at {DESKTOP_FILE_PATH}")
        return (True, f"Desktop launcher created!\n\nTalkType is now in your Applications menu.")

    except Exception as e:
        logger.error(f"Failed to create desktop launcher: {e}")
        return (False, f"Failed to create launcher: {e}")


def desktop_launcher_exists() -> bool:
    """
    Check if desktop launcher already exists.

    Returns:
        bool: True if launcher exists
    """
    return os.path.exists(DESKTOP_FILE_PATH)


def remove_desktop_launcher() -> Tuple[bool, str]:
    """
    Remove the desktop launcher.

    Returns:
        Tuple[bool, str]: (success, message)
    """
    try:
        if os.path.exists(DESKTOP_FILE_PATH):
            os.remove(DESKTOP_FILE_PATH)
            logger.info("Desktop launcher removed")
            return (True, "Desktop launcher removed.")
        else:
            return (True, "Desktop launcher was not installed.")
    except Exception as e:
        logger.error(f"Failed to remove desktop launcher: {e}")
        return (False, f"Failed to remove launcher: {e}")


def ensure_appimage_in_standard_location() -> Tuple[bool, str]:
    """
    Ensure the AppImage is in the standard location.

    If running from an AppImage that's not in ~/AppImages/, offer to copy it there.

    Returns:
        Tuple[bool, str]: (already_there, current_path)
            - already_there: True if AppImage is already in standard location
            - current_path: Path to the running AppImage (or None if not AppImage)
    """
    current_path = get_running_appimage_path()

    if not current_path:
        return (False, None)

    # Normalize paths for comparison
    current_normalized = os.path.realpath(current_path)
    standard_normalized = os.path.realpath(APPIMAGE_PATH)

    if current_normalized == standard_normalized:
        return (True, current_path)

    return (False, current_path)


def copy_appimage_to_standard_location() -> Tuple[bool, str]:
    """
    Copy the currently running AppImage to the standard location.

    Returns:
        Tuple[bool, str]: (success, message)
    """
    import shutil
    import stat

    current_path = get_running_appimage_path()
    if not current_path:
        return (False, "Not running from an AppImage.")

    try:
        # Ensure directory exists
        os.makedirs(APPIMAGE_DIR, exist_ok=True)

        # Copy AppImage
        shutil.copy2(current_path, APPIMAGE_PATH)

        # Make executable
        os.chmod(APPIMAGE_PATH, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

        logger.info(f"AppImage copied to {APPIMAGE_PATH}")
        return (True, f"AppImage installed to:\n{APPIMAGE_PATH}")

    except Exception as e:
        logger.error(f"Failed to copy AppImage: {e}")
        return (False, f"Failed to copy AppImage: {e}")


# For testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("Testing update checker...")
    print(f"Current version: {get_current_version()}")
    print(f"Extension version: {get_extension_version()}")
    print(f"Running from AppImage: {is_running_from_appimage()}")
    print(f"AppImage path: {get_running_appimage_path()}")
    print(f"Standard location: {APPIMAGE_PATH}")
    print(f"Desktop launcher exists: {desktop_launcher_exists()}")

    print("\nChecking for updates...")
    result = check_for_updates()

    if result["success"]:
        print(f"Latest version: {result['latest_version']}")
        print(f"Update available: {result['update_available']}")
        if result["release"]:
            print(f"Release URL: {result['release'].get('html_url')}")
            print(f"AppImage URL: {result['release'].get('appimage_url')}")
    else:
        print(f"Error: {result['error']}")

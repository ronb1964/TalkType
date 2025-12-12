"""
AT-SPI (Assistive Technology Service Provider Interface) integration for TalkType.

This module provides intelligent context detection and text insertion using the
AT-SPI accessibility framework. It enables:
- Detection of focused application and window context
- Reading text selection state
- Direct text insertion (more reliable than keystroke simulation)
- Application-specific behavior (code editors, terminals, chat windows, etc.)

Falls back gracefully to ydotool/wtype when AT-SPI is not available or not
supported by the target application.
"""

import logging
import shutil
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Try to import AT-SPI - it may not be available on all systems
_ATSPI_AVAILABLE = False
try:
    import gi
    gi.require_version('Atspi', '2.0')
    from gi.repository import Atspi
    _ATSPI_AVAILABLE = True
    logger.info("AT-SPI is available")
except (ImportError, ValueError) as e:
    logger.warning(f"AT-SPI not available: {e}")


@dataclass
class AppContext:
    """Information about the currently focused application/window."""
    app_name: str = ""              # Application name (e.g., "code", "firefox")
    role: str = ""                  # Widget role (e.g., "text", "terminal", "entry")
    is_editable: bool = False       # Can we insert text?
    supports_atspi: bool = False    # Does app support AT-SPI EditableText?
    has_selection: bool = False     # Is text currently selected?
    selection_start: int = 0        # Start of selection (character offset)
    selection_end: int = 0          # End of selection (character offset)
    caret_offset: int = 0           # Current cursor position
    is_password: bool = False       # Is this a password field?

    def __str__(self):
        return (f"AppContext(app={self.app_name}, role={self.role}, "
                f"editable={self.is_editable}, atspi={self.supports_atspi}, "
                f"selection={self.has_selection})")


def is_atspi_available() -> bool:
    """Check if AT-SPI is available on this system."""
    return _ATSPI_AVAILABLE


def get_focused_context() -> Optional[AppContext]:
    """
    Get context information about the currently focused application/widget.

    Returns:
        AppContext if successful, None if AT-SPI not available or no focus detected
    """
    if not _ATSPI_AVAILABLE:
        return None

    try:
        # Try multiple methods to find focused widget
        focused = None

        # Method 1: Find active window first (more reliable than FOCUSED)
        logger.debug("Attempting to find active window...")
        focused = _find_active_window()
        if focused:
            logger.debug("Found focus via active window search")

        # Method 2: Fall back to desktop traversal looking for FOCUSED state
        if not focused:
            logger.debug("Falling back to desktop traversal...")
            try:
                desktop = Atspi.get_desktop(0)
                if desktop:
                    focused = _find_focused_accessible(desktop)
                    if focused:
                        logger.debug("Found focus via desktop traversal")
            except Exception as e:
                logger.debug(f"Desktop traversal failed: {e}")

        if not focused:
            logger.debug("No focused accessible found via any method")
            return None

        # Build context from the focused accessible
        context = AppContext()

        # Get application name
        try:
            app = focused.get_application()
            if app:
                context.app_name = app.get_name() or ""
        except Exception as e:
            logger.debug(f"Could not get app name: {e}")

        # Get role
        try:
            role = focused.get_role()
            context.role = Atspi.role_get_name(role) if role else ""
        except Exception as e:
            logger.debug(f"Could not get role: {e}")

        # Check if it's a password field
        try:
            state_set = focused.get_state_set()
            if state_set:
                states = state_set.get_states()
                # Check for password/sensitive state
                if Atspi.StateType.SENSITIVE in states:
                    # This might be overly broad - refine based on testing
                    pass
                # Better check: role is PASSWORD_TEXT
                if context.role == "password text":
                    context.is_password = True
        except Exception as e:
            logger.debug(f"Could not check password state: {e}")

        # Try to get EditableText interface
        try:
            editable = focused.get_editable_text_iface()
            if editable:
                context.supports_atspi = True
                context.is_editable = True

                # Try to get text interface for selection info
                try:
                    text_iface = focused.get_text_iface()
                    if text_iface:
                        # Get current caret position
                        context.caret_offset = text_iface.get_caret_offset()

                        # Check for text selection
                        n_selections = text_iface.get_n_selections()
                        if n_selections > 0:
                            # Get first selection (usually there's only one)
                            selection = text_iface.get_selection(0)
                            if selection:
                                context.has_selection = True
                                context.selection_start = selection.start_offset
                                context.selection_end = selection.end_offset
                except Exception as e:
                    logger.debug(f"Could not get text selection info: {e}")
        except Exception as e:
            logger.debug(f"Could not get EditableText interface: {e}")

        # If no EditableText but has Text interface, it might still be editable
        # (some apps don't properly expose EditableText)
        if not context.is_editable:
            try:
                text_iface = focused.get_text_iface()
                if text_iface:
                    context.is_editable = True  # Assume editable if has text
            except Exception:
                pass

        logger.debug(f"Got focused context: {context}")
        return context

    except Exception as e:
        logger.error(f"Error getting focused context: {e}", exc_info=True)
        return None


def _find_focused_accessible(accessible, depth=0, max_depth=50) -> Optional:
    """
    Recursively search for the focused accessible widget.

    Args:
        accessible: AT-SPI accessible object to search
        depth: Current recursion depth (for limiting)
        max_depth: Maximum recursion depth

    Returns:
        The focused accessible, or None if not found
    """
    if not accessible or depth > max_depth:
        return None

    try:
        # Check if this widget has focus (or is active)
        state_set = accessible.get_state_set()
        if state_set:
            states = state_set.get_states()

            # Prefer FOCUSED, but also accept ACTIVE for windows
            if Atspi.StateType.FOCUSED in states:
                # Skip gnome-shell "Main stage" - that's the compositor, not a real widget
                name = accessible.get_name() or ""
                if "main stage" not in name.lower():
                    logger.debug(f"Found focused widget at depth {depth}: {name}")
                    return accessible

        # Recursively search children
        try:
            child_count = accessible.get_child_count()
            for i in range(child_count):
                try:
                    child = accessible.get_child_at_index(i)
                    if child:
                        result = _find_focused_accessible(child, depth + 1, max_depth)
                        if result:
                            return result
                except Exception:
                    # Skip problematic children
                    continue
        except Exception:
            pass

    except Exception:
        # Some accessibles may throw errors when queried - that's okay
        pass

    return None


def _find_active_window() -> Optional:
    """
    Find the currently active window by looking for ACTIVE state.
    This is more reliable than FOCUSED for window-level detection.
    """
    if not _ATSPI_AVAILABLE:
        return None

    try:
        desktop = Atspi.get_desktop(0)
        if not desktop:
            return None

        # Search all applications for an active window
        app_count = desktop.get_child_count()
        logger.debug(f"Searching {app_count} applications for active window")

        for i in range(app_count):
            try:
                app = desktop.get_child_at_index(i)
                if not app:
                    continue

                app_name = app.get_name() or ""
                logger.debug(f"Checking app: {app_name}")

                # Skip gnome-shell - we want real applications
                if app_name.lower() == "gnome-shell":
                    continue

                # Look for ACTIVE window in this app
                window_count = app.get_child_count()
                for j in range(window_count):
                    try:
                        window = app.get_child_at_index(j)
                        if not window:
                            continue

                        state_set = window.get_state_set()
                        if state_set:
                            states = state_set.get_states()
                            if Atspi.StateType.ACTIVE in states:
                                window_name = window.get_name() or ""
                                logger.debug(f"Found active window: {window_name} in {app_name}")

                                # Now find focused widget within this window
                                focused = _find_focused_accessible(window, depth=0, max_depth=30)
                                if focused:
                                    return focused

                                # If no focused widget, return the window itself
                                return window
                    except Exception:
                        continue
            except Exception:
                continue

        return None
    except Exception as e:
        logger.debug(f"Active window search failed: {e}")
        return None


def insert_text_atspi(text: str, context: Optional[AppContext] = None) -> bool:
    """
    Insert text using AT-SPI EditableText interface.

    If text is selected, this will replace the selection. Otherwise, inserts
    at current cursor position.

    Args:
        text: Text to insert
        context: Optional pre-fetched AppContext. If None, will fetch current context.

    Returns:
        True if insertion successful, False if failed or not supported
    """
    if not _ATSPI_AVAILABLE:
        logger.debug("AT-SPI not available for text insertion")
        return False

    # Get context if not provided
    if context is None:
        context = get_focused_context()

    if not context or not context.supports_atspi:
        logger.debug("AT-SPI text insertion not supported by current app")
        return False

    try:
        # Get the desktop and find focused widget again
        desktop = Atspi.get_desktop(0)
        if not desktop:
            return False

        focused = _find_focused_accessible(desktop)
        if not focused:
            return False

        # Get EditableText interface
        editable = focused.get_editable_text_iface()
        if not editable:
            return False

        # If text is selected, delete it first
        if context.has_selection:
            logger.debug(f"Deleting selected text: {context.selection_start}-{context.selection_end}")
            editable.delete_text(context.selection_start, context.selection_end)
            insert_pos = context.selection_start
        else:
            insert_pos = context.caret_offset

        # Insert the new text
        logger.debug(f"Inserting text at position {insert_pos}: {text[:50]}...")
        success = editable.insert_text(insert_pos, text, len(text))

        if success:
            # Move caret to end of inserted text
            new_caret_pos = insert_pos + len(text)
            try:
                text_iface = focused.get_text_iface()
                if text_iface:
                    text_iface.set_caret_offset(new_caret_pos)
            except Exception as e:
                logger.debug(f"Could not set caret position: {e}")

        return success

    except Exception as e:
        logger.error(f"AT-SPI text insertion failed: {e}", exc_info=True)
        return False


def is_vscode_active() -> bool:
    """
    Check if VS Code is the active application.

    Since VS Code (Electron) doesn't expose itself to AT-SPI, we detect it
    by checking running processes.

    Returns:
        True if VS Code appears to be active, False otherwise
    """
    try:
        import subprocess
        # Check for VS Code processes
        result = subprocess.run(
            ["pgrep", "-f", "code|Code"],
            capture_output=True,
            text=True
        )
        # If we have VS Code processes, assume it might be active
        # This is a heuristic - not perfect, but good enough
        return result.returncode == 0
    except Exception:
        return False


def is_terminal_active() -> bool:
    """
    Check if a terminal widget is currently focused.
    
    Terminal applications and terminal widgets (like VS Code's integrated terminal)
    use Shift+Ctrl+V for paste instead of Ctrl+V.
    
    This detects:
    - Standalone terminals: gnome-terminal, konsole, xterm, kitty, alacritty, etc.
    - Integrated terminals: VS Code terminal, embedded terminal widgets
    
    Returns:
        True if a terminal appears to be active, False otherwise
    """
    try:
        # First check: Use AT-SPI to check the role of the focused widget
        # This is the most accurate method and works for integrated terminals
        if _ATSPI_AVAILABLE:
            context = get_focused_context()
            if context:
                # Check if the widget role is "terminal"
                if context.role and "terminal" in context.role.lower():
                    logger.debug(f"Terminal detected by role: {context.role} in {context.app_name}")
                    return True
                
                # Check if app name contains terminal-related keywords
                if context.app_name:
                    app_lower = context.app_name.lower()
                    if any(term in app_lower for term in ["terminal", "konsole", "xterm", "kitty", "alacritty"]):
                        logger.debug(f"Terminal detected by app name: {context.app_name}")
                        return True
        
        # Second check: Window title detection (works for Electron apps)
        # This is crucial for VS Code/Cursor integrated terminals
        if is_terminal_window_by_title():
            return True
        
        # Third check: Process-based detection for standalone terminals
        # This is a fallback when AT-SPI doesn't provide clear info
        import subprocess
        terminal_patterns = [
            "gnome-terminal",
            "konsole",
            "xterm",
            "kitty",
            "alacritty",
            "terminator",
            "tilix",
            "urxvt",
            "rxvt",
            "xfce4-terminal",
            "mate-terminal",
            "lxterminal",
            "qterminal",
            "terminology",
            "foot",
            "wezterm"
        ]
        
        for pattern in terminal_patterns:
            result = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                # Found a running terminal process
                # If we have AT-SPI context and it doesn't match terminal, don't assume
                if _ATSPI_AVAILABLE:
                    # We already checked AT-SPI above, so if we got here, it's not focused
                    continue
                else:
                    # If AT-SPI not available, assume terminal is active if process exists
                    logger.debug(f"Terminal process detected (no AT-SPI): {pattern}")
                    return True
        
        return False
    except Exception as e:
        logger.debug(f"Terminal detection failed: {e}")
        return False


def _get_active_window_title() -> str:
    """
    Get the title of the currently active window.
    
    Works on both X11 and Wayland.
    
    Returns:
        Window title string, or empty string if unable to detect
    """
    try:
        import subprocess
        
        # Try xdotool first (X11)
        if shutil.which("xdotool"):
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.returncode == 0:
                return result.stdout.strip()
        
        # Try GNOME/Wayland via gdbus
        if shutil.which("gdbus"):
            try:
                # Get list of windows from GNOME Shell
                result = subprocess.run(
                    ["gdbus", "call", "--session",
                     "--dest", "org.gnome.Shell",
                     "--object-path", "/org/gnome/Shell/Extensions/Windows",
                     "--method", "org.gnome.Shell.Extensions.Windows.List"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    # Parse the output to find focused window
                    # The output is a JSON-like string with window info
                    output = result.stdout
                    # Look for "focus": true in the output and extract title
                    # This is a simplified approach - may need refinement
                    import json
                    try:
                        # Try to parse as JSON
                        data = json.loads(output)
                        for window in data:
                            if window.get('focus'):
                                return window.get('title', '')
                    except:
                        pass
            except Exception:
                pass
        
        # Try wmctrl with correct command (X11 or X-Wayland)
        if shutil.which("wmctrl"):
            result = subprocess.run(
                ["wmctrl", "-lp"],
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.returncode == 0:
                # Get active window ID from _NET_ACTIVE_WINDOW
                active_result = subprocess.run(
                    ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                if active_result.returncode == 0:
                    # Parse window ID from output like: "_NET_ACTIVE_WINDOW(WINDOW): window id # 0x1234567"
                    import re
                    match = re.search(r'0x[0-9a-fA-F]+', active_result.stdout)
                    if match:
                        active_id = match.group(0)
                        # Find this window in wmctrl output
                        for line in result.stdout.split('\n'):
                            if active_id in line:
                                # Window title is after the 4th column
                                parts = line.split(None, 3)
                                if len(parts) >= 4:
                                    return parts[3]
        
        # Last resort: try to get window info from /proc
        # This won't give us the title, but we can try to detect terminal processes
        
        return ""
    except Exception as e:
        logger.debug(f"Failed to get window title: {e}")
        return ""


def is_terminal_window_by_title() -> bool:
    """
    Check if the active window is a terminal based on its title.
    
    This is useful for Electron apps where AT-SPI doesn't expose widget details.
    Terminal windows typically have keywords like "Terminal", "bash", "zsh" in the title.
    
    Returns:
        True if window title suggests it's a terminal, False otherwise
    """
    try:
        import shutil
        title = _get_active_window_title()
        if not title:
            return False
        
        title_lower = title.lower()
        
        # Check for terminal-related keywords in window title
        terminal_keywords = [
            "terminal",
            "bash",
            "zsh",
            "fish",
            "sh",
            "powershell",
            "pwsh",
            "cmd",
            "command prompt",
            "konsole",
            "xterm",
            "gnome-terminal"
        ]
        
        for keyword in terminal_keywords:
            if keyword in title_lower:
                logger.debug(f"Terminal detected by window title: {title}")
                return True
        
        return False
    except Exception as e:
        logger.debug(f"Terminal window title detection failed: {e}")
        return False


def should_use_atspi(context: Optional[AppContext] = None) -> Tuple[bool, str]:
    """
    Determine if AT-SPI should be used for text insertion.

    Args:
        context: Optional pre-fetched AppContext

    Returns:
        Tuple of (should_use_atspi, reason_string)
    """
    if not _ATSPI_AVAILABLE:
        return (False, "AT-SPI not available")

    if context is None:
        context = get_focused_context()

    if not context:
        # Even without AT-SPI context, check if it's VS Code
        # VS Code doesn't expose AT-SPI, so we need process-based detection
        if is_vscode_active():
            return (False, "VS Code active - use typing to avoid paste duplication")
        return (False, "Could not get app context")

    if context.is_password:
        return (False, "Password field - use fallback for security")

    if not context.is_editable:
        return (False, "Not an editable widget")

    if not context.supports_atspi:
        return (False, "App does not support AT-SPI EditableText")

    # Success cases
    if context.has_selection:
        return (True, "Text selected - AT-SPI can replace directly")

    # For apps that support AT-SPI, prefer it for reliability
    return (True, "AT-SPI supported and reliable")


def get_diagnostic_info() -> dict:
    """
    Get diagnostic information about AT-SPI support and current focus.

    Useful for debugging and user support.

    Returns:
        Dictionary with diagnostic info
    """
    info = {
        "atspi_available": _ATSPI_AVAILABLE,
        "atspi_version": None,
        "focused_app": None,
        "context": None
    }

    if not _ATSPI_AVAILABLE:
        return info

    try:
        # Try to get AT-SPI version
        info["atspi_version"] = Atspi.get_version()
    except Exception:
        pass

    # Get current context
    context = get_focused_context()
    if context:
        info["focused_app"] = context.app_name
        info["context"] = {
            "app_name": context.app_name,
            "role": context.role,
            "editable": context.is_editable,
            "supports_atspi": context.supports_atspi,
            "has_selection": context.has_selection,
            "is_password": context.is_password
        }

    return info


# Quick self-test when run directly
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    print("AT-SPI Helper Self-Test")
    print("=" * 50)

    # Check availability
    print(f"\nAT-SPI Available: {is_atspi_available()}")

    if is_atspi_available():
        # Get diagnostic info
        info = get_diagnostic_info()
        print(f"\nAT-SPI Version: {info.get('atspi_version')}")
        print(f"\nFocused App: {info.get('focused_app')}")

        # Get current context
        print("\nCurrent Focus Context:")
        context = get_focused_context()
        if context:
            print(f"  App: {context.app_name}")
            print(f"  Role: {context.role}")
            print(f"  Editable: {context.is_editable}")
            print(f"  Supports AT-SPI: {context.supports_atspi}")
            print(f"  Has Selection: {context.has_selection}")
            if context.has_selection:
                print(f"  Selection: {context.selection_start}-{context.selection_end}")
            print(f"  Caret Offset: {context.caret_offset}")
            print(f"  Is Password: {context.is_password}")

            # Check if should use AT-SPI
            should_use, reason = should_use_atspi(context)
            print(f"\nShould use AT-SPI: {should_use}")
            print(f"Reason: {reason}")
        else:
            print("  No focused context found")
    else:
        print("\nAT-SPI is not available on this system")
        print("Text insertion will fall back to ydotool/wtype")

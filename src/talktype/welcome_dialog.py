#!/usr/bin/env python3
"""
Welcome Dialog for TalkType - First Launch Experience

Displays adaptive welcome screen based on detected system capabilities:
- Base welcome for all users
- Optional GNOME Shell Extension (if GNOME desktop detected)
- Optional CUDA Libraries (if NVIDIA GPU detected)

Cross-desktop compatible - works on GNOME, KDE, XFCE, etc.
"""

import os
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

try:
    from talktype.logger import setup_logger
    logger = setup_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


def detect_gnome_desktop():
    """
    Detect if running on GNOME desktop environment.

    Returns:
        bool: True if GNOME desktop is detected, False otherwise
    """
    # Check XDG_CURRENT_DESKTOP environment variable
    current_desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
    desktop_session = os.environ.get('DESKTOP_SESSION', '').lower()

    gnome_indicators = ['gnome', 'gnome-xorg', 'gnome-wayland']

    is_gnome = any(indicator in current_desktop for indicator in gnome_indicators) or \
               any(indicator in desktop_session for indicator in gnome_indicators)

    logger.debug(f"GNOME detection: XDG_CURRENT_DESKTOP={current_desktop}, "
                 f"DESKTOP_SESSION={desktop_session}, is_gnome={is_gnome}")

    return is_gnome


def detect_nvidia_gpu():
    """
    Detect if NVIDIA GPU is present in the system.

    Returns:
        bool: True if NVIDIA GPU is detected, False otherwise
    """
    try:
        # Check for nvidia-smi command (most reliable)
        result = os.popen('nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null').read()
        if result.strip():
            logger.debug(f"NVIDIA GPU detected: {result.strip()}")
            return True

        # Fallback: Check lspci
        result = os.popen('lspci 2>/dev/null | grep -i nvidia').read()
        if result.strip():
            logger.debug(f"NVIDIA GPU detected via lspci: {result.strip()}")
            return True

        logger.debug("No NVIDIA GPU detected")
        return False
    except Exception as e:
        logger.warning(f"Error detecting NVIDIA GPU: {e}")
        return False


class SplashScreen:
    """
    Simple splash screen showing TalkType icon.
    Fades in, shows briefly, then fades out before showing welcome dialog.
    """

    def __init__(self):
        """Create the splash screen window."""
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_title("TalkType")
        self.window.set_default_size(400, 400)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.set_decorated(False)  # No title bar
        self.window.set_keep_above(True)  # Stay on top
        self.window.set_type_hint(Gtk.WindowType.POPUP)  # Splash-style window

        # Enable transparency
        screen = self.window.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.window.set_visual(visual)
        self.window.set_app_paintable(True)

        # Transparent window with rounded dark box - glow will be animated via CSS classes
        self.css_provider = Gtk.CssProvider()
        self.css_provider.load_from_data(b"""
            window {
                background-color: transparent;
            }
            .splash-box {
                background-color: #262626;
                border-radius: 16px;
                padding: 80px;
            }
            image {
                padding: 0px;
                margin: 0px;
            }
            /* Glow animation states - grows radially from small to large with smoother steps */
            /* Using -gtk-icon-shadow which follows icon shape - 16 steps for smooth animation */
            image.glow-0  { -gtk-icon-shadow: 0 0 10px rgba(66, 133, 244, 0.4); }
            image.glow-1  { -gtk-icon-shadow: 0 0 15px rgba(66, 133, 244, 0.45); }
            image.glow-2  { -gtk-icon-shadow: 0 0 20px rgba(66, 133, 244, 0.5); }
            image.glow-3  { -gtk-icon-shadow: 0 0 25px rgba(66, 133, 244, 0.55); }
            image.glow-4  { -gtk-icon-shadow: 0 0 30px rgba(66, 133, 244, 0.6); }
            image.glow-5  { -gtk-icon-shadow: 0 0 35px rgba(66, 133, 244, 0.65); }
            image.glow-6  { -gtk-icon-shadow: 0 0 40px rgba(66, 133, 244, 0.7); }
            image.glow-7  { -gtk-icon-shadow: 0 0 45px rgba(66, 133, 244, 0.75); }
            image.glow-8  { -gtk-icon-shadow: 0 0 50px rgba(66, 133, 244, 0.8); }
            image.glow-9  { -gtk-icon-shadow: 0 0 55px rgba(66, 133, 244, 0.82), 0 0 90px rgba(66, 133, 244, 0.4); }
            image.glow-10 { -gtk-icon-shadow: 0 0 60px rgba(66, 133, 244, 0.84), 0 0 100px rgba(66, 133, 244, 0.5); }
            image.glow-11 { -gtk-icon-shadow: 0 0 65px rgba(66, 133, 244, 0.86), 0 0 110px rgba(66, 133, 244, 0.55); }
            image.glow-12 { -gtk-icon-shadow: 0 0 70px rgba(66, 133, 244, 0.88), 0 0 120px rgba(66, 133, 244, 0.6); }
            image.glow-13 { -gtk-icon-shadow: 0 0 75px rgba(66, 133, 244, 0.9), 0 0 130px rgba(66, 133, 244, 0.65); }
            image.glow-14 { -gtk-icon-shadow: 0 0 80px rgba(66, 133, 244, 0.95), 0 0 140px rgba(66, 133, 244, 0.7); }
            image.glow-15 { -gtk-icon-shadow: 0 0 90px rgba(66, 133, 244, 1.0), 0 0 160px rgba(66, 133, 244, 0.8); }
        """)
        # Apply CSS globally (needed for image child widget)
        Gtk.StyleContext.add_provider_for_screen(
            self.window.get_screen() if self.window.get_screen() else Gdk.Screen.get_default(),
            self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.glow_level = 0
        self.image_widget = None

        # Try to load icon from standard paths
        icon_path = None
        icon_paths = []

        # Check AppImage mount point first (has PNG in root)
        appimage_mount = os.environ.get('APPDIR')
        if appimage_mount:
            icon_paths.append(os.path.join(appimage_mount, "io.github.ronb1964.TalkType.png"))
            icon_paths.append(os.path.join(appimage_mount, "io.github.ronb1964.TalkType.svg"))
            icon_paths.append(os.path.join(appimage_mount, "usr", "share", "icons", "hicolor", "scalable", "apps", "io.github.ronb1964.TalkType.svg"))

        # Development/system paths - prioritize SVG for splash (cleaner rendering)
        icon_paths.extend([
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons", "OFFICIAL_ICON_DO_NOT_CHANGE.svg"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons", "TT_retro_square_light_transparent.png"),
            "/app/share/icons/hicolor/scalable/apps/io.github.ronb1964.TalkType.svg",
            "../icons/OFFICIAL_ICON_DO_NOT_CHANGE.svg",
            "../icons/TT_retro_square_light_transparent.png",
            "icons/OFFICIAL_ICON_DO_NOT_CHANGE.svg",
            os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps/io.github.ronb1964.TalkType.svg"),
        ])

        for path in icon_paths:
            if os.path.exists(path):
                icon_path = path
                logger.debug(f"Found splash icon at: {path}")
                break

        # Create centered icon image with rounded dark background
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        box.get_style_context().add_class('splash-box')

        if icon_path:
            try:
                # Load icon from file (works with both SVG and PNG)
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(icon_path, 256, 256)
                self.image_widget = Gtk.Image.new_from_pixbuf(pixbuf)
                box.pack_start(self.image_widget, False, False, 0)
                logger.info(f"Splash screen loaded icon from: {icon_path}")
            except Exception as e:
                logger.warning(f"Could not load splash icon from {icon_path}: {e}")
                # Fallback to text
                label = Gtk.Label(label="TalkType")
                label.set_markup('<span size="xx-large" weight="bold">TalkType</span>')
                box.pack_start(label, False, False, 0)
                self.image_widget = None
        else:
            # No icon found, use text
            logger.warning("No icon path found for splash screen")
            label = Gtk.Label(label="TalkType")
            label.set_markup('<span size="xx-large" weight="bold">TalkType</span>')
            box.pack_start(label, False, False, 0)
            self.image_widget = None

        self.window.add(box)

    def _animate_glow(self):
        """Animate the glow effect by expanding once to maximum, then staying there."""
        if not self.image_widget:
            return True

        style_context = self.image_widget.get_style_context()

        # Remove old glow class
        style_context.remove_class(f'glow-{self.glow_level}')

        # Increment glow level (0-15), but stop at maximum
        if self.glow_level < 15:
            self.glow_level += 1
            # Add new glow class
            style_context.add_class(f'glow-{self.glow_level}')
            return True  # Continue animation
        else:
            # Stay at maximum glow
            style_context.add_class(f'glow-{self.glow_level}')
            return False  # Stop animation

    def show_and_fade(self, callback):
        """
        Show splash screen, wait briefly, then fade out and call callback.

        Args:
            callback: Function to call after splash finishes (no arguments)
        """
        self.window.set_opacity(0.0)
        self.window.show_all()

        # Start glow animation (100ms per frame for faster animation)
        self.glow_timer = GLib.timeout_add(100, self._animate_glow)

        # Fade in over 300ms
        self._fade_in(0.0, callback)

    def _fade_in(self, opacity, callback):
        """Gradually increase opacity."""
        opacity += 0.05  # Slower fade in (20 steps)
        self.window.set_opacity(opacity)

        if opacity < 1.0:
            GLib.timeout_add(25, lambda: self._fade_in(opacity, callback))
        else:
            # Hold at full opacity for 2500ms (let glow expand once to max and hold), then fade out
            GLib.timeout_add(2500, lambda: self._fade_out(1.0, callback))

    def _fade_out(self, opacity, callback):
        """Gradually decrease opacity."""
        opacity -= 0.05  # Slower fade out (20 steps), matches fade in
        self.window.set_opacity(opacity)

        if opacity > 0.0:
            GLib.timeout_add(25, lambda: self._fade_out(opacity, callback))
        else:
            # Stop glow animation
            if hasattr(self, 'glow_timer'):
                GLib.source_remove(self.glow_timer)

            # Close splash and show welcome dialog
            self.window.destroy()
            callback()


class WelcomeDialog:
    """
    Adaptive welcome dialog that shows appropriate content based on system detection.

    Scenarios:
    1. Base only (no GNOME, no NVIDIA)
    2. Base + GNOME extension option
    3. Base + CUDA libraries option
    4. Base + both options
    """

    def __init__(self, parent=None, force_gnome=None, force_nvidia=None):
        """
        Initialize the welcome dialog.

        Args:
            parent: Parent window (optional)
            force_gnome: Override GNOME detection for testing (None/True/False)
            force_nvidia: Override NVIDIA detection for testing (None/True/False)
        """
        self.parent = parent

        # Detect system capabilities (or use forced values for testing)
        self.has_gnome = detect_gnome_desktop() if force_gnome is None else force_gnome
        self.has_nvidia = detect_nvidia_gpu() if force_nvidia is None else force_nvidia

        # Determine scenario
        if self.has_gnome and self.has_nvidia:
            self.scenario = 4
            self.height = 1245
        elif self.has_gnome:
            self.scenario = 2
            self.height = 1020
        elif self.has_nvidia:
            self.scenario = 3
            self.height = 1020
        else:
            self.scenario = 1
            self.height = 700

        logger.info(f"Welcome dialog scenario {self.scenario}: GNOME={self.has_gnome}, NVIDIA={self.has_nvidia}")

        # Build the dialog
        self.dialog = None
        self.extension_check = None
        self.cuda_check = None
        self._build_dialog()

    def _build_dialog(self):
        """Build the GTK dialog with appropriate content."""
        self.dialog = Gtk.Dialog(title="Welcome to TalkType!")
        self.dialog.set_default_size(580, self.height)
        self.dialog.set_resizable(False)
        self.dialog.set_modal(True)
        self.dialog.set_position(Gtk.WindowPosition.CENTER)

        if self.parent:
            self.dialog.set_transient_for(self.parent)

        # Dark theme
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-application-prefer-dark-theme", True)

        # Add CSS for checkbox styling with pulsating glow
        # Note: CSS needs to be applied globally (add_provider_for_screen) for child widgets,
        # but we use specific class names to avoid affecting other dialogs
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            /* Welcome dialog checkbox styles - using .welcome-checkbox class to avoid conflicts */
            .welcome-checkbox {
                padding: 8px;
                border-radius: 8px;
                transition: all 300ms ease-in-out;
            }
            .welcome-checkbox:hover {
                background-color: rgba(66, 133, 244, 0.15);
                box-shadow: 0 0 8px rgba(66, 133, 244, 0.3);
            }
            .welcome-checkbox:checked {
                background-color: rgba(66, 133, 244, 0.25);
                box-shadow: 0 0 12px rgba(66, 133, 244, 0.5);
            }
            /* Pulse effect with multiple states for smooth continuous animation */
            .welcome-checkbox.pulse-0 {
                background-color: rgba(66, 133, 244, 0.06);
                box-shadow: 0 0 8px rgba(66, 133, 244, 0.25);
            }
            .welcome-checkbox.pulse-1 {
                background-color: rgba(66, 133, 244, 0.075);
                box-shadow: 0 0 9px rgba(66, 133, 244, 0.3);
            }
            .welcome-checkbox.pulse-2 {
                background-color: rgba(66, 133, 244, 0.09);
                box-shadow: 0 0 11px rgba(66, 133, 244, 0.375);
            }
            .welcome-checkbox.pulse-3 {
                background-color: rgba(66, 133, 244, 0.105);
                box-shadow: 0 0 12px rgba(66, 133, 244, 0.425);
            }
            .welcome-checkbox.pulse-4 {
                background-color: rgba(66, 133, 244, 0.12);
                box-shadow: 0 0 14px rgba(66, 133, 244, 0.5);
            }
        """)
        # Apply CSS globally but with specific class names to avoid affecting other dialogs
        Gtk.StyleContext.add_provider_for_screen(
            self.dialog.get_screen() if self.dialog.get_screen() else Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Create scrolled window for content (handles small screens)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        content = self.dialog.get_content_area()
        content.pack_start(scrolled, True, True, 0)

        # VBox inside scrolled window
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        vbox.set_margin_start(30)
        vbox.set_margin_end(30)
        scrolled.add(vbox)

        # Build content sections
        self._build_header(vbox)
        self._build_base_content(vbox)

        # Add optional features if applicable
        if self.has_gnome or self.has_nvidia:
            self._build_optional_features(vbox)

        self._build_footer(vbox)

    def _build_header(self, vbox):
        """Build the header section."""
        # Header
        header = Gtk.Label()
        header.set_markup('<span size="x-large"><b>🎙️ Welcome to TalkType!</b></span>')
        vbox.pack_start(header, False, False, 0)

        # Subtitle
        subtitle = Gtk.Label()
        subtitle.set_markup('<span size="medium">AI-powered speech recognition for Linux</span>')
        subtitle.set_opacity(0.7)
        vbox.pack_start(subtitle, False, False, 0)

        # Separator
        sep1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        vbox.pack_start(sep1, False, False, 10)

    def _build_base_content(self, vbox):
        """Build the base content (shown in all scenarios)."""
        # Main description
        main_desc = Gtk.Label()
        main_desc.set_markup('<span size="medium">Privacy-focused, AI-powered dictation that runs entirely on your computer.</span>')
        main_desc.set_line_wrap(False)
        main_desc.set_justify(Gtk.Justification.CENTER)
        vbox.pack_start(main_desc, False, False, 10)

        # Key Features section
        features_label = Gtk.Label()
        features_label.set_markup('<span size="large"><b>✨ Key Features</b></span>')
        features_label.set_halign(Gtk.Align.START)
        vbox.pack_start(features_label, False, False, 5)

        # Features list
        features_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        features_box.set_margin_start(20)
        features_box.set_margin_top(5)

        features = [
            "🎤 <b>Press-and-hold dictation</b> (default: F8 key)",
            "🗣️ <b>Voice commands:</b> \"period\", \"comma\", \"new paragraph\"",
            "🤖 <b>Powered by OpenAI's Whisper AI</b>",
            "🔒 <b>100% local</b> - your voice never leaves your computer",
            "⚙️ <b>Configurable</b> hotkeys and preferences"
        ]

        for feature in features:
            label = Gtk.Label()
            label.set_markup(feature)
            label.set_halign(Gtk.Align.START)
            label.set_line_wrap(True)
            label.set_max_width_chars(60)
            features_box.pack_start(label, False, False, 0)

        vbox.pack_start(features_box, False, False, 0)

        # Separator
        sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep2.set_margin_top(10)
        sep2.set_margin_bottom(10)
        vbox.pack_start(sep2, False, False, 0)

        # Quick Start section
        quickstart_label = Gtk.Label()
        quickstart_label.set_markup('<span size="large"><b>💡 Quick Start</b></span>')
        quickstart_label.set_halign(Gtk.Align.START)
        vbox.pack_start(quickstart_label, False, False, 5)

        # Quick start tips
        quickstart_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        quickstart_box.set_margin_start(20)
        quickstart_box.set_margin_top(5)

        tips = [
            "Press your hotkey to start dictating",
            "Access settings from the system tray icon",
            "Click \"Help\" in the menu for documentation"
        ]

        for tip in tips:
            label = Gtk.Label()
            label.set_markup(f"• {tip}")
            label.set_halign(Gtk.Align.START)
            label.set_line_wrap(True)
            label.set_max_width_chars(60)
            quickstart_box.pack_start(label, False, False, 0)

        vbox.pack_start(quickstart_box, False, False, 0)

    def _build_optional_features(self, vbox):
        """Build the optional features section (GNOME extension and/or CUDA)."""
        # Separator before optional features
        sep3 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep3.set_margin_top(10)
        sep3.set_margin_bottom(10)
        vbox.pack_start(sep3, False, False, 0)

        # Optional Features header
        optional_label = Gtk.Label()
        optional_label.set_markup('<span size="large"><b>⚙️ Optional Features</b></span>')
        optional_label.set_halign(Gtk.Align.START)
        vbox.pack_start(optional_label, False, False, 5)

        # GNOME Extension (if detected)
        if self.has_gnome:
            self._build_gnome_extension_option(vbox)

        # CUDA Libraries (if detected)
        if self.has_nvidia:
            self._build_cuda_option(vbox)

        # Preferences note
        note = Gtk.Label()
        note.set_markup('<span size="small">💡 <i>You can install or change these anytime in Preferences → Advanced</i></span>')
        note.set_halign(Gtk.Align.START)
        note.set_margin_top(10)
        note.set_opacity(0.7)
        vbox.pack_start(note, False, False, 0)

    def _build_gnome_extension_option(self, vbox):
        """Build GNOME extension checkbox and details."""
        ext_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        ext_box.set_margin_start(20)
        ext_box.set_margin_top(5)

        # Checkbox with label
        self.extension_check = Gtk.CheckButton()
        self.extension_check.get_style_context().add_class('welcome-checkbox')
        ext_label = Gtk.Label()
        ext_label.set_markup('📦 <b>Install GNOME Extension</b> <span size="small">(~3KB)</span>')
        ext_label.set_halign(Gtk.Align.START)
        self.extension_check.add(ext_label)
        self.extension_check.set_tooltip_text(
            "Install native GNOME Shell extension for enhanced integration.\n"
            "Adds panel indicator, service controls, and enables custom recording indicator positioning on Wayland.\n"
            "Lightweight (~3KB) and requires logging out/in after installation."
        )
        ext_box.pack_start(self.extension_check, False, False, 0)

        # GNOME detected badge
        gnome_badge = Gtk.Label()
        gnome_badge.set_markup('<b>GNOME Desktop Detected!</b>')
        gnome_badge.set_halign(Gtk.Align.START)
        gnome_badge.set_margin_start(30)
        ext_box.pack_start(gnome_badge, False, False, 0)

        # Extension description
        ext_desc = Gtk.Label()
        ext_desc.set_markup('Add native desktop integration to your GNOME panel:')
        ext_desc.set_halign(Gtk.Align.START)
        ext_desc.set_margin_start(30)
        ext_desc.set_margin_top(5)
        ext_desc.set_opacity(0.9)
        ext_box.pack_start(ext_desc, False, False, 0)

        # Extension benefits
        ext_benefits = [
            "🔵 Panel indicator showing recording state",
            "🎮 Service start/stop controls",
            "✨ Visual feedback and notifications"
        ]

        ext_benefits_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        ext_benefits_box.set_margin_start(50)

        for benefit in ext_benefits:
            label = Gtk.Label()
            label.set_markup(benefit)
            label.set_halign(Gtk.Align.START)
            label.set_opacity(0.85)
            ext_benefits_box.pack_start(label, False, False, 0)

        ext_box.pack_start(ext_benefits_box, False, False, 0)

        # Requires log out note
        logout_note = Gtk.Label()
        logout_note.set_markup('<span size="small" style="italic">(Requires logging out and back in after installation)</span>')
        logout_note.set_halign(Gtk.Align.START)
        logout_note.set_margin_start(30)
        logout_note.set_margin_top(3)
        logout_note.set_opacity(0.7)
        ext_box.pack_start(logout_note, False, False, 0)

        vbox.pack_start(ext_box, False, False, 0)

    def _build_cuda_option(self, vbox):
        """Build CUDA libraries checkbox and details."""
        cuda_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cuda_box.set_margin_start(20)
        cuda_box.set_margin_top(10)

        # Checkbox with label
        self.cuda_check = Gtk.CheckButton()
        self.cuda_check.get_style_context().add_class('welcome-checkbox')
        cuda_label = Gtk.Label()
        cuda_label.set_markup('📦 <b>Download CUDA Libraries</b> <span size="small">(~800MB)</span>')
        cuda_label.set_halign(Gtk.Align.START)
        self.cuda_check.add(cuda_label)
        self.cuda_check.set_tooltip_text(
            "Download NVIDIA CUDA libraries for GPU-accelerated transcription.\n"
            "Provides 3-5x faster performance with your NVIDIA graphics card.\n"
            "Download is ~800MB and may take a few minutes depending on connection speed.\n"
            "GPU mode will be automatically enabled after successful download."
        )
        cuda_box.pack_start(self.cuda_check, False, False, 0)

        # NVIDIA detected badge
        nvidia_badge = Gtk.Label()
        nvidia_badge.set_markup('<b>NVIDIA GPU Detected!</b>')
        nvidia_badge.set_halign(Gtk.Align.START)
        nvidia_badge.set_margin_start(30)
        cuda_box.pack_start(nvidia_badge, False, False, 0)

        # CUDA description
        cuda_desc = Gtk.Label()
        cuda_desc.set_markup('Enable GPU-accelerated speech recognition:')
        cuda_desc.set_halign(Gtk.Align.START)
        cuda_desc.set_margin_start(30)
        cuda_desc.set_margin_top(5)
        cuda_desc.set_opacity(0.9)
        cuda_box.pack_start(cuda_desc, False, False, 0)

        # CUDA benefits
        cuda_benefits = [
            "⚡ 3-5x faster transcription speed",
            "🎯 Better accuracy for longer recordings",
            "💻 Lower CPU usage during transcription"
        ]

        cuda_benefits_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        cuda_benefits_box.set_margin_start(45)

        for benefit in cuda_benefits:
            label = Gtk.Label()
            label.set_markup(benefit)
            label.set_halign(Gtk.Align.START)
            label.set_opacity(0.85)
            cuda_benefits_box.pack_start(label, False, False, 0)

        cuda_box.pack_start(cuda_benefits_box, False, False, 0)

        # Storage note
        storage_note = Gtk.Label()
        from talktype.config import get_data_dir
        data_dir = get_data_dir()
        storage_note.set_markup(f'<span size="small" style="italic">(Libraries will be stored in {data_dir}/)</span>')
        storage_note.set_halign(Gtk.Align.START)
        storage_note.set_margin_start(30)
        storage_note.set_margin_top(3)
        storage_note.set_opacity(0.7)
        cuda_box.pack_start(storage_note, False, False, 0)

        vbox.pack_start(cuda_box, False, False, 0)

    def _build_footer(self, vbox):
        """Build the footer section."""
        # Next steps note
        next_label = Gtk.Label()
        next_label.set_markup('<span><b>Next:</b> You\'ll test your hotkeys to ensure they work correctly</span>')
        next_label.set_halign(Gtk.Align.START)
        next_label.set_line_wrap(True)
        next_label.set_margin_top(10)
        next_label.set_opacity(0.8)
        vbox.pack_start(next_label, False, False, 0)

        # Centered "Let's Go!" button
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.set_margin_top(15)

        continue_btn = Gtk.Button(label="Let's Go!")
        continue_btn.set_size_request(200, 40)
        continue_btn.get_style_context().add_class("suggested-action")
        continue_btn.connect("clicked", lambda w: self.dialog.response(Gtk.ResponseType.OK))

        button_box.pack_start(continue_btn, False, False, 0)
        vbox.pack_start(button_box, False, False, 0)

    def _pulse_checkboxes(self):
        """Animate checkboxes with smooth continuous pulsating glow."""
        import math

        checkboxes = []
        if self.extension_check:
            checkboxes.append(self.extension_check)
        if self.cuda_check:
            checkboxes.append(self.cuda_check)

        if not checkboxes:
            return False  # Stop animation if no checkboxes

        # Smooth continuous pulse using sin wave
        phase = getattr(self, '_pulse_phase', 0)
        self._pulse_phase = phase + 0.15  # Even faster increment for more noticeable pulse

        # Calculate pulse intensity (oscillates smoothly between 0 and 4)
        # Using sin wave that goes from dim (0) to bright (4) and back
        intensity = 2 + 2 * math.sin(phase)  # Range: 0 to 4

        # Map to one of 5 pulse states (0=dimmest, 4=brightest)
        pulse_level = int(round(intensity))

        for checkbox in checkboxes:
            if not checkbox.get_active():  # Only pulse unchecked boxes
                style_context = checkbox.get_style_context()

                # Remove all pulse classes
                for i in range(5):
                    style_context.remove_class(f'pulse-{i}')

                # Add the current pulse level class
                style_context.add_class(f'pulse-{pulse_level}')

        return True  # Continue animation

    def _fade_in_dialog(self, opacity):
        """Fade in the dialog gradually."""
        opacity += 0.05
        self.dialog.set_opacity(opacity)

        if opacity < 1.0:
            GLib.timeout_add(25, lambda: self._fade_in_dialog(opacity))

    def run(self):
        """
        Show the dialog and return user selections.

        Returns:
            dict: User selections with keys:
                - 'install_extension': bool (if GNOME detected)
                - 'download_cuda': bool (if NVIDIA detected)
                - 'continue': bool (True if user clicked "Let's Go!")
        """
        # Show dialog and fade in
        self.dialog.set_opacity(0.0)
        self.dialog.show_all()
        self._fade_in_dialog(0.0)

        # Start pulsating animation for checkboxes (50ms for smooth continuous pulse)
        self._pulse_phase = 0
        pulse_timer = GLib.timeout_add(50, self._pulse_checkboxes)

        response = self.dialog.run()

        # Stop pulsating animation
        GLib.source_remove(pulse_timer)

        result = {'continue': response == Gtk.ResponseType.OK}

        if self.extension_check:
            result['install_extension'] = self.extension_check.get_active()

        if self.cuda_check:
            result['download_cuda'] = self.cuda_check.get_active()

        logger.info(f"Welcome dialog result: {result}")

        return result

    def destroy(self):
        """Destroy the dialog."""
        if self.dialog:
            self.dialog.destroy()


def show_welcome_dialog(parent=None):
    """
    Convenience function to show the welcome dialog with splash screen.

    Args:
        parent: Parent window (optional)

    Returns:
        dict: User selections from the dialog
    """
    result_container = [None]  # Use list to store result from callback

    def show_dialog_after_splash():
        """Called after splash screen finishes."""
        dialog = WelcomeDialog(parent=parent)
        result_container[0] = dialog.run()
        dialog.destroy()
        Gtk.main_quit()

    # Show splash screen first
    splash = SplashScreen()
    splash.show_and_fade(show_dialog_after_splash)

    # Run GTK main loop until dialog closes
    Gtk.main()

    return result_container[0]


def show_tips_and_features_dialog():
    """
    Show tips and features dialog after hotkey testing.
    Encourages users to explore TalkType's capabilities.
    """
    dialog = Gtk.Dialog(title="TalkType - Setup Complete!")
    dialog.set_default_size(600, 500)
    dialog.set_border_width(0)
    dialog.set_resizable(False)

    # Get content area
    content = dialog.get_content_area()
    content.set_spacing(0)

    # Main container with padding
    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
    vbox.set_margin_start(30)
    vbox.set_margin_end(30)
    vbox.set_margin_top(25)
    vbox.set_margin_bottom(25)
    content.pack_start(vbox, True, True, 0)

    # Success header
    header_label = Gtk.Label()
    header_label.set_markup('<span size="xx-large">🎉</span>')
    vbox.pack_start(header_label, False, False, 0)

    title_label = Gtk.Label()
    title_label.set_markup('<span size="x-large"><b>You\'re All Set!</b></span>')
    vbox.pack_start(title_label, False, False, 0)

    subtitle_label = Gtk.Label()
    subtitle_label.set_markup('<span>TalkType is ready to use. Here are some tips to get you started:</span>')
    subtitle_label.set_line_wrap(True)
    subtitle_label.set_max_width_chars(50)
    subtitle_label.set_justify(Gtk.Justification.CENTER)
    vbox.pack_start(subtitle_label, False, False, 5)

    # Separator
    sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
    sep.set_margin_top(10)
    sep.set_margin_bottom(10)
    vbox.pack_start(sep, False, False, 0)

    # Tips section
    tips_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

    tips = [
        ("🎤 <b>Voice Commands</b>", "Say \"period\", \"comma\", \"new paragraph\" and more to punctuate naturally"),
        ("⚙️ <b>Smart Features</b>", "Auto-punctuation and auto-spacing are enabled by default for smooth dictation"),
        ("🔧 <b>Customize Settings</b>", "Right-click the tray icon to access Preferences - adjust models, hotkeys, and more"),
        ("📖 <b>Learn More</b>", "Click \"Help\" in the tray menu for full documentation and voice command list"),
        ("🚀 <b>Quick Start</b>", "Press your hotkey and start talking - TalkType does the rest!")
    ]

    for title, description in tips:
        tip_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)

        title_label = Gtk.Label()
        title_label.set_markup(title)
        title_label.set_halign(Gtk.Align.START)
        title_label.set_line_wrap(True)
        title_label.set_max_width_chars(60)
        tip_box.pack_start(title_label, False, False, 0)

        desc_label = Gtk.Label()
        desc_label.set_markup(f'<span size="small">{description}</span>')
        desc_label.set_halign(Gtk.Align.START)
        desc_label.set_line_wrap(True)
        desc_label.set_max_width_chars(60)
        desc_label.set_margin_start(20)
        desc_label.set_opacity(0.9)
        tip_box.pack_start(desc_label, False, False, 0)

        tips_box.pack_start(tip_box, False, False, 0)

    vbox.pack_start(tips_box, False, False, 0)

    # Bottom section - encourage exploration
    sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
    sep2.set_margin_top(15)
    sep2.set_margin_bottom(10)
    vbox.pack_start(sep2, False, False, 0)

    encourage_label = Gtk.Label()
    encourage_label.set_markup(
        '<span size="small"><i>💡 Explore the Preferences to discover more features like\n'
        'GPU acceleration, different model sizes, and custom punctuation!</i></span>'
    )
    encourage_label.set_line_wrap(True)
    encourage_label.set_justify(Gtk.Justification.CENTER)
    encourage_label.set_opacity(0.8)
    vbox.pack_start(encourage_label, False, False, 0)

    # Get Started button with proper padding
    button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    button_box.set_margin_top(10)
    button_box.set_margin_bottom(10)
    button_box.set_margin_start(20)
    button_box.set_margin_end(20)

    get_started_button = Gtk.Button(label="Get Started!")
    get_started_button.connect("clicked", lambda b: dialog.response(Gtk.ResponseType.OK))
    get_started_button.get_style_context().add_class("suggested-action")
    get_started_button.set_size_request(120, -1)  # Minimum width

    button_box.pack_end(get_started_button, False, False, 0)
    dialog.get_action_area().pack_start(button_box, True, True, 0)

    dialog.show_all()
    dialog.run()
    dialog.destroy()


def show_hotkey_test_dialog():
    """
    Show hotkey testing dialog for first-run experience.
    Allows users to test and customize both hotkeys in one place.

    Returns:
        bool: True if user completed the test
    """
    from talktype.config import load_config, save_config

    config = load_config()

    dialog = Gtk.Dialog(title="Test Your Hotkeys")
    dialog.set_default_size(550, 420)
    dialog.set_modal(True)
    dialog.set_position(Gtk.WindowPosition.CENTER)

    content = dialog.get_content_area()
    content.set_margin_top(20)
    content.set_margin_bottom(20)
    content.set_margin_start(25)
    content.set_margin_end(25)
    content.set_spacing(15)

    # Instructions
    instructions = Gtk.Label()
    instructions.set_markup('<span size="large"><b>Configure Your Hotkeys</b></span>\n\nTest both hotkeys to ensure they work on your system:')
    instructions.set_xalign(0)
    content.pack_start(instructions, False, False, 0)

    # State variables
    current_hold_key = [config.hotkey]
    current_toggle_key = [config.toggle_hotkey]
    tested_keys = {"hold": False, "toggle": False}
    capturing_key = [None]  # "hold", "toggle", or None

    # Hotkey configuration box with buttons
    hotkey_config_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    hotkey_config_box.set_margin_top(10)

    # Push-to-talk row
    hold_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    hold_label = Gtk.Label()
    hold_label.set_markup(f'<b>Push-to-talk:</b> {current_hold_key[0]}')
    hold_label.set_xalign(0)
    hold_label.set_size_request(200, -1)
    hold_row.pack_start(hold_label, False, False, 0)

    hold_change_btn = Gtk.Button(label="Change Key")
    hold_change_btn.set_size_request(120, -1)
    hold_row.pack_start(hold_change_btn, False, False, 0)

    hold_status = Gtk.Label()
    hold_status.set_markup('<span color="#999999">Not tested</span>')
    hold_status.set_xalign(0)
    hold_row.pack_start(hold_status, True, True, 0)

    hotkey_config_box.pack_start(hold_row, False, False, 0)

    # Toggle mode row
    toggle_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    toggle_label = Gtk.Label()
    toggle_label.set_markup(f'<b>Toggle mode:</b> {current_toggle_key[0]}')
    toggle_label.set_xalign(0)
    toggle_label.set_size_request(200, -1)
    toggle_row.pack_start(toggle_label, False, False, 0)

    toggle_change_btn = Gtk.Button(label="Change Key")
    toggle_change_btn.set_size_request(120, -1)
    toggle_row.pack_start(toggle_change_btn, False, False, 0)

    toggle_status = Gtk.Label()
    toggle_status.set_markup('<span color="#999999">Not tested</span>')
    toggle_status.set_xalign(0)
    toggle_row.pack_start(toggle_status, True, True, 0)

    hotkey_config_box.pack_start(toggle_row, False, False, 0)

    content.pack_start(hotkey_config_box, False, False, 0)

    # Capture instruction (hidden initially)
    capture_instruction = Gtk.Label()
    capture_instruction.set_markup('<span background="#FFA500" color="white"> Press any key to set hotkey... (ESC to cancel) </span>')
    capture_instruction.set_margin_top(10)
    capture_instruction.set_no_show_all(True)
    content.pack_start(capture_instruction, False, False, 0)

    # Key press event handler
    def on_key_press(widget, event):
        keyname = Gtk.accelerator_name(event.keyval, 0)

        # If we're capturing a new key
        if capturing_key[0]:
            if keyname == "Escape":
                # Cancel capture
                capturing_key[0] = None
                capture_instruction.hide()
                hold_change_btn.set_sensitive(True)
                toggle_change_btn.set_sensitive(True)
                return True

            # Update the appropriate key
            if capturing_key[0] == "hold":
                current_hold_key[0] = keyname
                hold_label.set_markup(f'<b>Push-to-talk:</b> {keyname}')
                tested_keys["hold"] = True
                hold_status.set_markup('<span color="#4CAF50">✓ Working!</span>')
            elif capturing_key[0] == "toggle":
                current_toggle_key[0] = keyname
                toggle_label.set_markup(f'<b>Toggle mode:</b> {keyname}')
                tested_keys["toggle"] = True
                toggle_status.set_markup('<span color="#4CAF50">✓ Working!</span>')

            capturing_key[0] = None
            capture_instruction.hide()
            hold_change_btn.set_sensitive(True)
            toggle_change_btn.set_sensitive(True)
            return True

        # Normal testing mode
        if keyname == current_hold_key[0]:
            tested_keys["hold"] = True
            hold_status.set_markup('<span color="#4CAF50">✓ Working!</span>')
        elif keyname == current_toggle_key[0]:
            tested_keys["toggle"] = True
            toggle_status.set_markup('<span color="#4CAF50">✓ Working!</span>')

        return True

    # Change button handlers
    def on_change_hold(button):
        capturing_key[0] = "hold"
        capture_instruction.show()
        hold_change_btn.set_sensitive(False)
        toggle_change_btn.set_sensitive(False)

    def on_change_toggle(button):
        capturing_key[0] = "toggle"
        capture_instruction.show()
        hold_change_btn.set_sensitive(False)
        toggle_change_btn.set_sensitive(False)

    hold_change_btn.connect("clicked", on_change_hold)
    toggle_change_btn.connect("clicked", on_change_toggle)

    # Connect key press handler
    dialog.connect("key-press-event", on_key_press)

    # Info label
    info_label = Gtk.Label()
    info_label.set_markup(
        '<span size="small"><i>💡 Both hotkeys will be saved to your configuration.\n'
        'You can change between Push-to-talk and Toggle mode anytime in Preferences.</i></span>'
    )
    info_label.set_line_wrap(True)
    info_label.set_xalign(0)
    info_label.set_margin_top(15)
    content.pack_start(info_label, False, False, 0)

    # Note about conflicts
    conflict_label = Gtk.Label()
    conflict_label.set_markup(
        '<span size="small"><i>⚠️ If a key doesn\'t respond, it may be used by another application.</i></span>'
    )
    conflict_label.set_line_wrap(True)
    conflict_label.set_xalign(0)
    conflict_label.set_opacity(0.8)
    content.pack_start(conflict_label, False, False, 0)

    # Continue button
    continue_button = Gtk.Button(label="Continue")

    def on_continue(button):
        # Save the keys to config
        config.hotkey = current_hold_key[0]
        config.toggle_hotkey = current_toggle_key[0]
        save_config(config)
        dialog.response(Gtk.ResponseType.OK)

    continue_button.connect("clicked", on_continue)
    continue_button.get_style_context().add_class("suggested-action")
    dialog.add_action_widget(continue_button, Gtk.ResponseType.OK)

    dialog.show_all()
    response = dialog.run()
    dialog.destroy()

    return response == Gtk.ResponseType.OK


def show_welcome_and_install():
    """
    Show welcome dialog and handle optional installations.
    This is the main entry point for first-run experience.

    Returns:
        dict: Result dictionary with installation status
    """
    # Show the welcome dialog
    result = show_welcome_dialog()

    if not result or not result.get('continue'):
        logger.info("User cancelled welcome dialog")
        return result

    # Handle CUDA libraries download FIRST (takes longer)
    if result.get('download_cuda'):
        logger.info("User requested CUDA libraries download")

        # Show confirmation dialog first
        confirm_dialog = Gtk.MessageDialog(
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Download CUDA Libraries?"
        )
        from talktype.config import get_data_dir
        cuda_path = os.path.join(get_data_dir(), "cuda")
        confirm_dialog.format_secondary_text(
            "This will download approximately 800MB of CUDA libraries for GPU acceleration.\n\n"
            f"The files will be stored in {cuda_path} and may take several minutes to download.\n\n"
            "Continue with download?"
        )
        confirm_dialog.set_position(Gtk.WindowPosition.CENTER)
        response = confirm_dialog.run()
        confirm_dialog.destroy()

        if response != Gtk.ResponseType.YES:
            logger.info("CUDA download cancelled by user")
        else:
            try:
                from talktype import cuda_helper

                # Use the unified modern download dialog
                cuda_helper.show_cuda_download_dialog()

            except Exception as e:
                logger.error(f"Error during CUDA libraries download: {e}")

    # Handle GNOME extension installation SECOND (quick, and user may want to logout)
    if result.get('install_extension'):
        logger.info("User requested GNOME extension installation")
        try:
            from talktype import extension_helper

            # Show progress dialog
            progress_dialog = Gtk.MessageDialog(
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.NONE,
                text="Installing GNOME Extension..."
            )
            progress_dialog.format_secondary_text("Please wait while we install the TalkType extension...")
            progress_dialog.show_all()

            # Process pending events to show the dialog
            while Gtk.events_pending():
                Gtk.main_iteration()

            # Attempt installation
            success = extension_helper.download_and_install_extension()
            progress_dialog.destroy()

            if success:
                # Show success message with logout reminder
                msg = Gtk.MessageDialog(
                    message_type=Gtk.MessageType.INFO,
                    buttons=Gtk.ButtonsType.OK,
                    text="GNOME Extension Installed!"
                )
                msg.format_secondary_text(
                    "The TalkType extension has been installed successfully.\n\n"
                    "Please log out and back in for the extension to become active."
                )
                msg.run()
                msg.destroy()
                logger.info("GNOME extension installed successfully")
            else:
                # Show error message
                msg = Gtk.MessageDialog(
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Installation Failed"
                )
                msg.format_secondary_text(
                    "Could not install the GNOME extension.\n\n"
                    "You can try again later from Preferences → Advanced."
                )
                msg.run()
                msg.destroy()
                logger.error("GNOME extension installation failed")

        except Exception as e:
            logger.error(f"Error during GNOME extension installation: {e}")

    # Show hotkey testing dialog
    logger.info("Showing hotkey test dialog")
    show_hotkey_test_dialog()

    # Show tips and features dialog
    logger.info("Showing tips and features dialog")
    show_tips_and_features_dialog()
    logger.info("First-run setup completed")

    return result


if __name__ == '__main__':
    # Test the welcome dialog
    Gtk.init(None)
    result = show_welcome_dialog()
    print(f"Welcome dialog result: {result}")

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
from gi.repository import Gtk

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
            self.height = 1220
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
        ext_label = Gtk.Label()
        ext_label.set_markup('📦 <b>Install GNOME Extension</b> <span size="small">(~3KB)</span>')
        ext_label.set_halign(Gtk.Align.START)
        self.extension_check.add(ext_label)
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
        cuda_label = Gtk.Label()
        cuda_label.set_markup('📦 <b>Download CUDA Libraries</b> <span size="small">(~800MB)</span>')
        cuda_label.set_halign(Gtk.Align.START)
        self.cuda_check.add(cuda_label)
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
        storage_note.set_markup('<span size="small" style="italic">(Libraries will be stored in ~/.local/share/TalkType/)</span>')
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

    def run(self):
        """
        Show the dialog and return user selections.

        Returns:
            dict: User selections with keys:
                - 'install_extension': bool (if GNOME detected)
                - 'download_cuda': bool (if NVIDIA detected)
                - 'continue': bool (True if user clicked "Let's Go!")
        """
        self.dialog.show_all()
        response = self.dialog.run()

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
    Convenience function to show the welcome dialog.

    Args:
        parent: Parent window (optional)

    Returns:
        dict: User selections from the dialog
    """
    dialog = WelcomeDialog(parent=parent)
    result = dialog.run()
    dialog.destroy()
    return result


def show_hotkey_test_dialog():
    """
    Show hotkey testing dialog for first-run experience.
    Simplified version that just shows the test interface.

    Returns:
        bool: True if user completed the test
    """
    from talktype.config import Config

    config = Config()

    dialog = Gtk.Dialog(title="Test Your Hotkeys")
    dialog.set_default_size(450, 280)
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
    instructions.set_markup('<span size="large"><b>Test Your Hotkeys</b></span>\n\nPress each hotkey to verify it works:')
    instructions.set_xalign(0)
    content.pack_start(instructions, False, False, 0)

    # Get current hotkeys
    hold_key = config.get("hotkey", "F8")
    toggle_key = config.get("toggle_hotkey", "F9")
    mode = config.get("mode", "hold")

    # Test status labels
    status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    status_box.set_margin_top(10)

    hold_label = Gtk.Label()
    hold_label.set_markup(f'<b>{hold_key}</b> (Push-to-talk): <span color="#999999">Not tested</span>')
    hold_label.set_xalign(0)
    status_box.pack_start(hold_label, False, False, 0)

    toggle_label = Gtk.Label()
    if mode == "toggle":
        toggle_label.set_markup(f'<b>{toggle_key}</b> (Toggle mode): <span color="#999999">Not tested</span>')
    else:
        toggle_label.set_markup(f'<b>{toggle_key}</b> (Toggle mode): <span color="#999999">Not used in Hold mode</span>')
    toggle_label.set_xalign(0)
    status_box.pack_start(toggle_label, False, False, 0)

    content.pack_start(status_box, False, False, 0)

    # Track tested keys
    tested_keys = {"hold": False, "toggle": False}

    # Key press event handler
    def on_key_press(widget, event):
        keyname = Gtk.accelerator_name(event.keyval, 0)

        if keyname == hold_key:
            tested_keys["hold"] = True
            hold_label.set_markup(f'<b>{hold_key}</b> (Push-to-talk): <span color="#4CAF50">✓ Working!</span>')
        elif keyname == toggle_key and mode == "toggle":
            tested_keys["toggle"] = True
            toggle_label.set_markup(f'<b>{toggle_key}</b> (Toggle mode): <span color="#4CAF50">✓ Working!</span>')

        return True  # Stop event propagation

    # Connect key press handler to dialog
    dialog.connect("key-press-event", on_key_press)

    # Info label
    info_label = Gtk.Label()
    info_label.set_markup('<i>Note: If a key doesn\'t work, it may be used by another application.\nYou can change hotkeys anytime in Preferences → Hotkeys.</i>')
    info_label.set_line_wrap(True)
    info_label.set_xalign(0)
    info_label.set_margin_top(10)
    content.pack_start(info_label, False, False, 0)

    # Continue button
    continue_button = Gtk.Button(label="Continue")
    continue_button.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))
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
        try:
            from talktype import cuda_helper

            # Show progress dialog
            progress_dialog = Gtk.MessageDialog(
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.NONE,
                text="Downloading CUDA Libraries..."
            )
            progress_dialog.format_secondary_text(
                "Please wait while we download CUDA libraries (~800MB).\n"
                "This may take several minutes depending on your connection..."
            )
            progress_dialog.show_all()

            # Process pending events to show the dialog
            while Gtk.events_pending():
                Gtk.main_iteration()

            # Attempt download
            success = cuda_helper.download_cuda_libraries()
            progress_dialog.destroy()

            if success:
                # Show success message
                msg = Gtk.MessageDialog(
                    message_type=Gtk.MessageType.INFO,
                    buttons=Gtk.ButtonsType.OK,
                    text="CUDA Libraries Downloaded!"
                )
                msg.format_secondary_text(
                    "GPU acceleration is now available.\n\n"
                    "TalkType will use your NVIDIA GPU for faster transcription."
                )
                msg.run()
                msg.destroy()
                logger.info("CUDA libraries downloaded successfully")
            else:
                # Show error message
                msg = Gtk.MessageDialog(
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Download Failed"
                )
                msg.format_secondary_text(
                    "Could not download CUDA libraries.\n\n"
                    "You can try again later from Preferences → Advanced."
                )
                msg.run()
                msg.destroy()
                logger.error("CUDA libraries download failed")

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

    # Show setup complete message
    msg = Gtk.MessageDialog(
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text="Setup Complete!"
    )
    msg.format_secondary_text(
        "TalkType is ready to use!\n\n"
        "• Press your hotkey to start dictating\n"
        "• Access settings from the system tray icon\n"
        "• Click 'Help' in the menu for tips and documentation"
    )
    msg.run()
    msg.destroy()
    logger.info("First-run setup completed")

    return result


if __name__ == '__main__':
    # Test the welcome dialog
    Gtk.init(None)
    result = show_welcome_dialog()
    print(f"Welcome dialog result: {result}")

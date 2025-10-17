#!/usr/bin/env python3
"""
Test Welcome Dialog - Scenario 3: NVIDIA GPU Only
Shows: Base structure + Optional CUDA Libraries feature
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

def show_welcome_scenario3():
    """Welcome dialog for NVIDIA GPU users (no GNOME)"""

    dialog = Gtk.Dialog(title="Welcome to TalkType!")
    dialog.set_default_size(580, 1020)
    dialog.set_resizable(False)
    dialog.set_modal(True)
    dialog.set_position(Gtk.WindowPosition.CENTER)

    # Dark theme
    settings = Gtk.Settings.get_default()
    if settings:
        settings.set_property("gtk-application-prefer-dark-theme", True)

    # Create scrolled window for content (handles small screens)
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

    content = dialog.get_content_area()
    content.pack_start(scrolled, True, True, 0)

    # VBox inside scrolled window
    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
    vbox.set_margin_top(20)
    vbox.set_margin_bottom(20)
    vbox.set_margin_start(30)
    vbox.set_margin_end(30)
    scrolled.add(vbox)

    # ========== BASE STRUCTURE (ALWAYS SHOWN) ==========

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

    # Features list (medium/default text size)
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

    # Quick start tips (medium/default text size)
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

    # ========== OPTIONAL FEATURES SECTION (CUDA ONLY) ==========

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

    # CUDA checkbox and details
    cuda_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    cuda_box.set_margin_start(20)
    cuda_box.set_margin_top(5)

    # Checkbox with label
    cuda_check = Gtk.CheckButton()
    cuda_label = Gtk.Label()
    cuda_label.set_markup('📦 <b>Download CUDA Libraries</b> <span size="small">(~800MB)</span>')
    cuda_label.set_halign(Gtk.Align.START)
    cuda_check.add(cuda_label)
    cuda_box.pack_start(cuda_check, False, False, 0)

    # NVIDIA detected badge (no background color)
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

    benefits_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
    benefits_box.set_margin_start(45)

    for benefit in cuda_benefits:
        label = Gtk.Label()
        label.set_markup(benefit)
        label.set_halign(Gtk.Align.START)
        label.set_opacity(0.85)
        benefits_box.pack_start(label, False, False, 0)

    cuda_box.pack_start(benefits_box, False, False, 0)

    # Storage note
    storage_note = Gtk.Label()
    storage_note.set_markup('<span size="small" style="italic">(Libraries will be stored in ~/.local/share/TalkType/)</span>')
    storage_note.set_halign(Gtk.Align.START)
    storage_note.set_margin_start(30)
    storage_note.set_margin_top(3)
    storage_note.set_opacity(0.7)
    cuda_box.pack_start(storage_note, False, False, 0)

    vbox.pack_start(cuda_box, False, False, 0)

    # ========== BOTTOM SECTION (ALWAYS SHOWN) ==========

    # Info note about preferences
    note = Gtk.Label()
    note.set_markup('<span size="small">💡 <i>You can install or change these anytime in Preferences → Advanced</i></span>')
    note.set_halign(Gtk.Align.START)
    note.set_margin_top(10)
    note.set_opacity(0.7)
    vbox.pack_start(note, False, False, 0)

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
    continue_btn.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))

    button_box.pack_start(continue_btn, False, False, 0)
    vbox.pack_start(button_box, False, False, 0)

    dialog.show_all()
    response = dialog.run()

    result = {
        'download_cuda': cuda_check.get_active(),
        'continue': response == Gtk.ResponseType.OK
    }

    dialog.destroy()
    return result

if __name__ == '__main__':
    Gtk.init(None)
    result = show_welcome_scenario3()
    print(f"Result: {result}")

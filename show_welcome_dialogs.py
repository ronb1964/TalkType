#!/usr/bin/env python3
"""
Script to display TalkType welcome dialogs for screenshots.
Run this to show each dialog one at a time for screenshots.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

def show_cuda_welcome():
    """Show the CUDA welcome dialog."""
    dialog = Gtk.Dialog(title="Welcome to TalkType!")
    dialog.set_default_size(600, 450)
    dialog.set_modal(True)
    dialog.set_position(Gtk.WindowPosition.CENTER)

    # Dark theme
    settings = Gtk.Settings.get_default()
    if settings:
        settings.set_property("gtk-application-prefer-dark-theme", True)

    content = dialog.get_content_area()
    content.set_margin_top(20)
    content.set_margin_bottom(20)
    content.set_margin_start(20)
    content.set_margin_end(20)

    # Header with emoji
    header = Gtk.Label()
    header.set_markup('<span size="x-large">🎮 <b>NVIDIA GPU Detected!</b></span>')
    header.set_margin_bottom(15)
    content.pack_start(header, False, False, 0)

    # Main message
    msg = Gtk.Label()
    msg.set_markup('Your system has an NVIDIA graphics card that can significantly accelerate TalkType speech recognition.')
    msg.set_line_wrap(True)
    msg.set_max_width_chars(60)
    msg.set_margin_bottom(15)
    content.pack_start(msg, False, False, 0)

    # Benefits box
    benefits_frame = Gtk.Frame()
    benefits_frame.set_shadow_type(Gtk.ShadowType.IN)
    benefits_frame.set_margin_bottom(15)

    benefits_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    benefits_box.set_margin_top(12)
    benefits_box.set_margin_bottom(12)
    benefits_box.set_margin_start(15)
    benefits_box.set_margin_end(15)

    benefits_title = Gtk.Label()
    benefits_title.set_markup('<b>🚀 GPU Acceleration Benefits:</b>')
    benefits_title.set_xalign(0)
    benefits_box.pack_start(benefits_title, False, False, 0)

    benefits = [
        "⚡ 3-5x faster transcription speed",
        "🎯 Better accuracy for longer recordings",
        "⏱️ Real-time processing for live dictation",
        "💻 Lower CPU usage during transcription"
    ]

    for benefit in benefits:
        label = Gtk.Label(label=f"  {benefit}")
        label.set_xalign(0)
        benefits_box.pack_start(label, False, False, 0)

    benefits_frame.add(benefits_box)
    content.pack_start(benefits_frame, False, False, 0)

    # Download info
    download_info = Gtk.Label()
    download_info.set_markup('<b>📦 One-time setup:</b> ~800MB download\nLibraries stored in ~/.local/share/TalkType/')
    download_info.set_margin_bottom(15)
    content.pack_start(download_info, False, False, 0)

    # Note about enabling later
    note = Gtk.Label()
    note.set_markup('<i>You can also enable GPU acceleration later in Preferences → Advanced</i>')
    note.set_line_wrap(True)
    content.pack_start(note, False, False, 0)

    # Buttons
    dialog.add_button("Skip for Now", Gtk.ResponseType.CANCEL)
    dialog.add_button("Download CUDA Libraries", Gtk.ResponseType.OK)

    dialog.show_all()
    response = dialog.run()
    dialog.destroy()
    return response == Gtk.ResponseType.OK


def show_initial_help():
    """Show the initial help dialog (for users who skip CUDA)."""
    dialog = Gtk.Dialog(title="Welcome to TalkType")
    dialog.set_default_size(520, 320)
    dialog.set_resizable(False)
    dialog.set_modal(True)
    dialog.set_position(Gtk.WindowPosition.CENTER)
    content = dialog.get_content_area()
    content.set_margin_top(20)
    content.set_margin_bottom(20)
    content.set_margin_start(25)
    content.set_margin_end(25)
    content.set_spacing(15)

    # Main instructions
    instructions = Gtk.Label()
    instructions.set_markup('''<span size="large"><b>🎙️ Welcome to TalkType!</b></span>

<b>🚀 Next Steps:</b>

<b>1. Verify Your Hotkeys</b>
   After clicking "Got It!", you'll test your hotkeys (F8 and F9)
   to ensure they work and don't conflict with other apps.

<b>2. Start Dictating!</b>
   Once verified, the service starts automatically.
   Press <b>F8</b> (push-to-talk) or <b>F9</b> (toggle mode) to dictate.

<b>✨ Key Features:</b>
• Auto-punctuation, smart quotes, 50+ languages
• GPU acceleration available (3-5x faster with NVIDIA GPU)
• Auto-timeout after 5 minutes to save system resources

<b>🎮 GPU Acceleration:</b>
Enable later for faster transcription:
Right-click tray → "Preferences" → "Advanced" tab

<b>📚 Need Help?</b>
Right-click the tray icon → "Help..." for full documentation''')
    instructions.set_line_wrap(True)
    instructions.set_xalign(0)
    instructions.set_yalign(0)
    content.pack_start(instructions, True, True, 0)

    # Buttons
    button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    button_box.set_halign(Gtk.Align.CENTER)

    got_it_btn = Gtk.Button(label="Got It!")
    got_it_btn.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))
    button_box.pack_start(got_it_btn, False, False, 0)

    content.pack_start(button_box, False, False, 0)

    dialog.show_all()
    dialog.run()
    dialog.destroy()


def main():
    """Main function to display dialogs."""
    print("TalkType Welcome Dialog Screenshot Tool")
    print("=" * 50)
    print("\n1. CUDA Welcome Dialog")
    print("2. Initial Help Dialog")
    print("3. Both (one after another)")
    print("q. Quit")

    choice = input("\nWhich dialog would you like to display? (1/2/3/q): ").strip()

    if choice == '1':
        print("\nShowing CUDA Welcome Dialog...")
        print("Take your screenshot, then close the dialog.")
        show_cuda_welcome()
    elif choice == '2':
        print("\nShowing Initial Help Dialog...")
        print("Take your screenshot, then close the dialog.")
        show_initial_help()
    elif choice == '3':
        print("\nShowing CUDA Welcome Dialog first...")
        print("Take your screenshot, then close to see the next dialog.")
        show_cuda_welcome()
        print("\nShowing Initial Help Dialog...")
        print("Take your screenshot, then close the dialog.")
        show_initial_help()
    elif choice.lower() == 'q':
        print("Goodbye!")
        return
    else:
        print("Invalid choice. Please run again and choose 1, 2, 3, or q.")
        return

    print("\nDone! Screenshots ready.")


if __name__ == "__main__":
    main()

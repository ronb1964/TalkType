"""
TalkType Help Dialog - Shared help window for tray and preferences.

The content is format-aware: TalkType ships as a Flatpak, an AppImage, and
.deb/.rpm/AUR packages, and some instructions differ (hotkeys, typing method,
file paths, updates, troubleshooting). Rather than maintain separate help files,
this one dialog branches on how TalkType is installed — the same runtime
detection (FLATPAK_ID / get_install_type) that onboarding, Preferences, and the
updater use. Change it once, every format stays correct.
"""
import os

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


def _install_facts():
    """Format-specific strings the help text interpolates. One place to keep the
    Flatpak vs non-Flatpak differences straight."""
    is_flatpak = bool(os.environ.get("FLATPAK_ID"))
    app_id = "io.github.ronb1964.TalkType"
    if is_flatpak:
        cfg_dir = f"~/.var/app/{app_id}/config/talktype/"
        cache_dir = f"~/.var/app/{app_id}/cache/huggingface/"
    else:
        cfg_dir = "~/.config/talktype/"
        cache_dir = "~/.cache/huggingface/"
    return {
        "is_flatpak": is_flatpak,
        "cfg_dir": cfg_dir,
        "cache_dir": cache_dir,
        "log_path": cfg_dir + "talktype.log",
    }


def show_help_dialog():
    """Show help dialog with TalkType features and instructions."""
    from gi.repository import Gdk

    f = _install_facts()
    is_flatpak = f["is_flatpak"]

    # --- format-aware phrasing --------------------------------------------------
    if is_flatpak:
        keys_line = ("the two keys you assigned during setup — one to "
                     "<b>Hold to talk</b>, one to <b>Toggle dictation</b>")
        keys_where = ("your desktop's <b>System Settings → Keyboard → Shortcuts</b> "
                      "(find <b>TalkType</b> under Applications)")
        hotkey_hold = "your <b>Hold-to-talk</b> key"
        hotkey_toggle = "your <b>Toggle-dictation</b> key"
    else:
        keys_line = ("<b>F8</b> to hold-to-talk and <b>F9</b> to tap-to-toggle "
                     "(both active at once)")
        keys_where = "<b>Preferences → General</b>"
        hotkey_hold = "<b>F8</b>"
        hotkey_toggle = "<b>F9</b>"

    if is_flatpak:
        typing_para = (
            "TalkType types straight into the focused app through your desktop's "
            "secure input portal (libei) — there's no typing setup to configure, "
            "and clipboard paste isn't used.")
    else:
        typing_para = (
            "• <b>Keyboard Simulation (default):</b> types text using ydotool/wtype.\n"
            "• <b>Clipboard Paste:</b> copies to the clipboard then simulates "
            "Ctrl+V — use it if typing doesn't work in a particular app.")

    # "no hotkey works" troubleshooting differs completely by format.
    if is_flatpak:
        no_hotkey_block = (
            "<b>No hotkey works at all (dictation never starts):</b>\n"
            "• On the Flatpak your keys are assigned by the desktop, not by TalkType.\n"
            f"• Open {keys_where} and make sure a key is set for both "
            "<b>Hold to talk</b> and <b>Toggle dictation</b>.\n"
            "• If the assign prompt never appeared on first run, restart TalkType "
            "(tray → Restart Service) and it will ask again.")
    else:
        no_hotkey_block = (
            "<b>No hotkey works at all (dictation never starts):</b>\n"
            "• TalkType reads your keyboard directly, which requires your user "
            "account to be in the system's \"input\" group. Without it, no key can "
            "be detected.\n"
            "• Go to <b>Preferences → Advanced → Typing Setup</b> and click "
            "<b>\"Fix Typing Permissions\"</b>. You'll be asked for your admin password.\n"
            "• <b>Then restart your computer.</b> Logging out and back in is often "
            "not enough — a background session keeps the old permissions alive.\n"
            "• Most common on Fedora, where the setting that lets TalkType type is "
            "granted separately from the one that lets it read your keys.")

    # KDE-on-Flatpak: the per-dictation "remote control" popup.
    kde_notice = ""
    if is_flatpak and "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", ""):
        kde_notice = (
            "\n\n<b>Turning off KDE's per-dictation popup:</b>\n"
            "KDE shows a \"Remote control session started\" popup each time TalkType "
            "types. To stop it, use the <b>🔔</b> button in <b>Preferences → General</b>, "
            "or: click the sliders icon on that popup → under <b>Started Remote "
            "Desktop</b> uncheck <b>Show a message in a pop-up</b> → Apply.")

    # Update guidance per install type.
    if is_flatpak:
        update_block = (
            "TalkType updates through Flatpak. Run <tt>flatpak update "
            "io.github.ronb1964.TalkType</tt>, or use your software center — the "
            "built-in \"Check for Updates\" points you at the same command.")
    else:
        update_block = (
            "Updating matches how you installed TalkType:\n"
            "   – <b>.deb / .rpm:</b> click \"Download &amp; Install\" — it downloads "
            "the new package and installs it through your system package manager "
            "(you'll be asked for your password once), then offers to restart.\n"
            "   – <b>AppImage:</b> click \"Download &amp; Install\" — it swaps in the "
            "new version and restarts automatically.\n"
            "   – <b>Arch (AUR):</b> update with your AUR helper, e.g. "
            "<tt>yay -S talktype-appimage</tt>.")

    first_run_hotkey_bullet = (
        "" if is_flatpak
        else "• Tests your hotkeys (F8 and F9) to ensure they work\n")

    dialog = Gtk.Dialog(title="TalkType Help")
    dialog.set_default_size(650, 550)

    # Set minimum size but allow resizing larger
    geo = Gdk.Geometry()
    geo.min_width = 500
    geo.min_height = 400
    dialog.set_geometry_hints(None, geo, Gdk.WindowHints.MIN_SIZE)

    dialog.set_resizable(True)  # Allow resizing
    dialog.set_modal(False)  # Non-modal so it works without parent window
    dialog.set_position(Gtk.WindowPosition.CENTER)
    dialog.set_keep_above(True)  # Ensure it appears on top

    content = dialog.get_content_area()
    content.set_margin_top(10)
    content.set_margin_bottom(10)
    content.set_margin_start(10)
    content.set_margin_end(10)

    # Create notebook (tabbed interface)
    notebook = Gtk.Notebook()
    notebook.set_tab_pos(Gtk.PositionType.TOP)
    content.pack_start(notebook, True, True, 0)

    # Helper function to create a tab with scrolled content
    def create_tab(title, markup_text):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_margin_top(15)
        scrolled.set_margin_bottom(15)
        scrolled.set_margin_start(20)
        scrolled.set_margin_end(20)

        label = Gtk.Label()
        label.set_markup(markup_text)
        label.set_line_wrap(True)
        label.set_xalign(0)
        label.set_valign(Gtk.Align.START)

        scrolled.add(label)
        tab_label = Gtk.Label(label=title)
        tab_label.set_halign(Gtk.Align.CENTER)  # Center text within the tab
        tab_label.set_hexpand(True)             # Expand to fill tab width
        notebook.append_page(scrolled, tab_label)

    # Tab 1: Getting Started
    create_tab("🚀 Getting Started", f'''<span size="large"><b>Quick Start Guide</b></span>

<b>✨ TalkType is ready to use!</b>
The dictation service starts automatically when you launch TalkType.

<b>🎉 First-Run Setup</b>
On first launch, TalkType shows a welcome dialog that:
{first_run_hotkey_bullet}• Offers to install the GNOME extension (if on GNOME desktop)
• Offers to download CUDA libraries (if an NVIDIA GPU is detected)
• Adapts automatically to your system capabilities

<b>1. Begin Dictating</b>
Both keys are always active at once — {keys_line}.
• <b>Recording Indicator:</b> a red microphone icon appears during active dictation.

<b>2. Configure Settings</b>
Right-click → "Preferences" to customize the AI model, language, GPU acceleration,
beeps, and more. (Dictation keys are set in {keys_where}.)

<b>3. Dictate!</b>
Press your key and speak clearly at a normal pace.
Text is inserted where your cursor is.

<b>💡 Auto-Timeout Feature:</b>
The service automatically pauses after 5 minutes of inactivity to save
system resources. Adjust this in Preferences → Advanced.

<b>Need more help?</b> Check the other tabs for detailed information.''')

    # Tab 2: Features
    create_tab("✨ Features", f'''<span size="large"><b>Key Features</b></span>

<b>Two Keys, Always Active</b>
• Hold-to-talk AND tap-to-toggle work simultaneously ({keys_line})
• Visual recording indicator on screen during active recording
• Audio beeps for start/stop feedback

<b>Performance Mode Presets</b>
Quick one-click optimization via tray menu:
• <b>Fastest:</b> Tiny model, CPU - instant results
• <b>Balanced:</b> Small model, GPU - good accuracy with speed
• <b>Most Accurate:</b> Large-v3 model, GPU - best quality
• <b>Battery Saver:</b> Tiny model, CPU, short timeout

<b>Smart Text Processing</b>
• Auto-punctuation for natural text flow
• Smart quotes (" " instead of " ")
• Auto-spacing before new text
• Optional auto-period at end of sentences
• Voice-activated undo (word, sentence, paragraph, or everything)

<b>Language Support</b>
• Auto-detect language from speech
• Manually select from 50+ supported languages
• Great for multilingual users

<b>Audio Control</b>
• Microphone selection and testing
• Audio level monitoring
• Volume adjustment support

<b>System Integration</b>
• Launch at login option
• System tray integration (GTK or GNOME extension)
• Notification sounds (optional)
• Desktop notifications (optional)''')

    # Tab 3: AI Models
    create_tab("🤖 AI Models", '''<span size="large"><b>Choosing the Right AI Model</b></span>

Configure in: Preferences → General → Model

<b>Available Models:</b>

<b>• tiny (39 MB)</b>
  Speed: ⚡⚡⚡⚡⚡ Fastest
  Accuracy: ⭐⭐ Basic
  Best for: Quick notes, casual use

<b>• base (74 MB)</b>
  Speed: ⚡⚡⚡⚡ Fast
  Accuracy: ⭐⭐⭐ Good
  Best for: Casual dictation

<b>• small (244 MB)</b>
  Speed: ⚡⚡⚡ Balanced
  Accuracy: ⭐⭐⭐⭐ Very good
  Best for: General use (recommended)

<b>• medium (769 MB)</b>
  Speed: ⚡⚡ Slower
  Accuracy: ⭐⭐⭐⭐⭐ Excellent
  Best for: Professional dictation

<b>• large-v3 (~3 GB)</b>
  Speed: ⚡ Slowest
  Accuracy: ⭐⭐⭐⭐⭐⭐ Best possible
  Best for: Technical/professional work
  ⚠️ Takes 30-60 seconds to load initially, 10-20 seconds after

<b>Benefits of Larger Models:</b>
• Better recognition of uncommon words and technical terms
• More accurate with proper nouns and acronyms
• Improved punctuation and capitalization
• Better handling of accents and background noise
• Superior context awareness (e.g., "their" vs "there")
• More natural sentence structure

<b>Recommendation:</b>
Start with "small" for everyday use. Upgrade to "medium" or "large-v3"
if you need better accuracy for professional or technical dictation.''')

    # Tab 4: Advanced
    create_tab("⚙️ Advanced", f'''<span size="large"><b>Advanced Features</b></span>

<b>🎮 GPU Acceleration</b>
If you have an NVIDIA graphics card, enable GPU acceleration for 3-5x faster transcription:
• On first run with an NVIDIA GPU, you'll be offered to download CUDA libraries (~1.4GB)
• After download completes, click OK or Apply in Preferences to activate GPU mode
• Device automatically switches to "CUDA (GPU)" - no manual selection needed
• GPU mode significantly reduces transcription time (3-5x faster)
• Allows use of larger models without slowdown
• Can also download CUDA later: Preferences → Advanced → "Download CUDA Libraries"

<b>🔋 Power Management</b>
TalkType includes intelligent timeout to save system resources:
• <b>Auto-timeout:</b> Service stops automatically after inactivity
• <b>Configurable:</b> Set duration in Preferences → Advanced
• <b>Smart detection:</b> Timer resets when you use hotkeys
• <b>Battery friendly:</b> Reduces CPU/GPU usage when idle

<b>📝 Text Injection</b>
{typing_para}

<b>🎛️ Audio Settings</b>
Fine-tune audio in Preferences → Audio tab:
• Select specific microphone
• Test audio levels
• Adjust input volume (PulseAudio systems)
• Enable/disable audio beeps''')

    # Tab 5: Voice Commands
    create_tab("🗣️ Voice Commands", '''<span size="large"><b>Voice Commands Reference</b></span>

Use these spoken commands during dictation to insert punctuation and formatting.

<b>💡 Quick Access:</b> Set a Voice Commands hotkey in Preferences → General
to pop up a compact cheat sheet anytime. Also available from the tray menu.

<b>Punctuation:</b>
• Say <b>comma</b> for ,
• Say <b>period</b> or <b>full stop</b> for .
• Say <b>question mark</b> for ?
• Say <b>exclamation point</b> or <b>exclamation mark</b> for !
• Say <b>semicolon</b> for ;
• Say <b>colon</b> for :
• Say <b>apostrophe</b> for '
• Say <b>quote</b> for regular "
• Say <b>open quote</b> or <b>open quotes</b> for "
• Say <b>close quote</b> or <b>close quotes</b> for "
• Say <b>hyphen</b> or <b>dash</b> for -
• Say <b>em dash</b> for —
• Say <b>dot dot dot</b> or <b>ellipsis</b> for …

<b>Brackets &amp; Parentheses:</b>
• Say <b>open parenthesis</b> for (
• Say <b>close parenthesis</b> for )
• Say <b>open bracket</b> for [
• Say <b>close bracket</b> for ]
• Say <b>open brace</b> for {
• Say <b>close brace</b> for }

<b>Formatting:</b>
• Say <b>new line</b>, <b>newline</b>, <b>return</b>, or <b>line break</b> for a line break
• Say <b>new paragraph</b> or <b>paragraph break</b> for a double line break
• Say <b>tab</b> for a tab character (indent)
• Say <b>soft break</b> or <b>soft line</b> for three spaces

<b>Literal Words:</b>
To output the word instead of executing the command, say <b>literal</b> or <b>the word</b> before it:

• <b>literal period</b> or <b>the word period</b> → "period" (not .)
• <b>literal comma</b> or <b>the word comma</b> → "comma" (not ,)
• <b>literal tab</b> or <b>the word tab</b> → "tab" (not a tab character)
• <b>literal new line</b> or <b>the word newline</b> → "newline" (not a line break)
• <b>literal question mark</b> → "question mark" (not ?)
• <b>literal exclamation point</b> → "exclamation point" (not !)

Works with most voice commands!

<b>Usage Examples:</b>
Say: <i>Hello world comma how are you question mark</i>
Result: Hello world, how are you?

Say: <i>First sentence period new line Second sentence exclamation point</i>
Result: First sentence.
Second sentence!

Say: <i>The temperature is 98 point 6 degrees</i>
Result: The temperature is 98.6 degrees

<b>Custom Voice Commands:</b>
Define your own phrase → replacement shortcuts in Preferences → Commands tab.

Examples:
• "my email" → "user@example.com"
• "my address" → "123 Main Street, City, ST 12345"

To inject a replacement exactly as typed — bypassing auto-capitalization
and punctuation — wrap the replacement text in double quotes.

<b>Undo Commands:</b>
• Say <b>undo last word</b> to delete the last word you dictated
• Say <b>undo last sentence</b> to delete back to the previous sentence
• Say <b>undo last paragraph</b> to delete back to the last line break
• Say <b>undo everything</b> or <b>delete everything</b> to clear the field
• Also works: <b>delete last word</b>, <b>remove last word</b>, <b>clear all</b>, etc.

<b>Smart Features:</b>
• Auto-capitalization after sentences
• Auto-period added if a sentence has no punctuation
• Smart quote placement and spacing''')

    # Tab 6: Tips
    create_tab("💡 Tips", f'''<span size="large"><b>Tips &amp; Troubleshooting</b></span>

<b>Keyboard Shortcuts:</b>
• {hotkey_hold}: push-to-talk (hold to record, release to stop)
• {hotkey_toggle}: toggle recording (press once to start, again to stop)
• <b>Voice Commands shortcut:</b> set in Preferences → General to pop up the cheat sheet
• Keys work globally in any application
• Change your dictation keys in {keys_where}

<b>Getting Best Results:</b>
• Speak clearly at a normal pace
• Use a quality microphone for better accuracy
• Minimize background noise
• Pause briefly at sentence ends for better punctuation

<b>Status Indicators:</b>
• Tray icon shows service status (bright = running, dimmed = stopped)
• Red recording indicator appears on screen during dictation
• Audio beeps indicate recording start/stop (can be disabled)

<b>Installation &amp; Updates:</b>
• <b>Check for updates:</b> the tray/panel menu, or Preferences → Updates tab.
• {update_block}
• <b>Config files:</b> {f["cfg_dir"]}
• <b>AI models:</b> {f["cache_dir"]}

<b>Common Issues:</b>

<b>Hotkey not working:</b>
• Check if another app is using the same key
• Re-assign it in {keys_where}
• Ensure the service is running

{no_hotkey_block}

<b>Text not inserting:</b>
• Make sure the cursor is in a text field
• Give the target app a moment to focus before speaking

<b>Transcription too slow:</b>
• Enable GPU acceleration if you have an NVIDIA GPU
• Try a smaller AI model (tiny/base/small)
• Use Performance presets in the tray menu

<b>Service won't start:</b>
• Check logs: {f["log_path"]}
• Restart from the tray menu: Stop Service then Start Service{kde_notice}

<b>Bug Reports &amp; Feedback:</b>
Found a bug or have a feature request? We'd love to hear from you!

• <b>Report bugs:</b> https://github.com/ronb1964/TalkType/issues
• <b>Include:</b> your Linux distro, desktop environment, and TalkType version
• <b>Log file:</b> {f["log_path"]}

Your feedback helps make TalkType better for everyone!''')

    # Close button
    close_button = Gtk.Button(label="Close")
    close_button.connect("clicked", lambda w: dialog.destroy())
    dialog.add_action_widget(close_button, Gtk.ResponseType.CLOSE)

    # Connect response to destroy (for non-blocking operation)
    dialog.connect("response", lambda d, r: d.destroy())

    dialog.show_all()
    dialog.present()  # Bring to front and focus

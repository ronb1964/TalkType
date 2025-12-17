"""
TalkType Help Dialog - Shared help window for tray and preferences.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


def show_help_dialog():
    """Show help dialog with TalkType features and instructions."""
    from gi.repository import Gdk

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
        notebook.append_page(scrolled, tab_label)

    # Tab 1: Getting Started (merged best of tray + prefs)
    create_tab("🚀 Getting Started", '''<span size="large"><b>Quick Start Guide</b></span>

<b>✨ TalkType is ready to use!</b>
The dictation service starts automatically when you launch TalkType.

<b>🎉 First-Run Setup</b>
On first launch, TalkType shows a welcome dialog that:
• Tests your hotkeys (F8 and F9) to ensure they work
• Offers to install GNOME extension (if on GNOME desktop)
• Offers to download CUDA libraries (if NVIDIA GPU detected)
• Adapts automatically to your system capabilities

<b>1. Begin Dictating</b>
Press <b>F8</b> (push-to-talk) or <b>F9</b> (toggle mode) to start
• <b>F8:</b> Hold to record, release to stop
• <b>F9:</b> Press once to start, press again to stop
• <b>Recording Indicator:</b> A red microphone icon appears during active dictation

<b>2. Configure Settings</b>
Right-click → "Preferences" to customize:
• Hotkeys (F8/F9 or custom keys)
• AI model (tiny to large-v3)
• Language (auto-detect or select manually)
• GPU acceleration (if you have NVIDIA GPU)
• Text input method (keyboard or clipboard)

<b>3. Dictate!</b>
Press your hotkey and speak clearly at a normal pace.
Text will be inserted where your cursor is located.

<b>💡 Auto-Timeout Feature:</b>
The service automatically pauses after 5 minutes of inactivity to save
system resources. Adjust this in Preferences → Advanced.

<b>Need more help?</b> Check the other tabs for detailed information.''')

    # Tab 2: Features
    create_tab("✨ Features", '''<span size="large"><b>Key Features</b></span>

<b>Dual Hotkey Modes</b>
• F8 (push-to-talk) or F9 (toggle) - fully customizable
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

<b>Flexible Text Input</b>
• <b>Auto:</b> Automatically detects best method for each app
• <b>Keyboard Typing:</b> Character-by-character typing
• <b>Clipboard Paste:</b> Fast paste using Ctrl+Shift+V (works everywhere)

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
    create_tab("⚙️ Advanced", '''<span size="large"><b>Advanced Features</b></span>

<b>🎮 GPU Acceleration</b>
If you have an NVIDIA graphics card, enable GPU acceleration for 3-5x faster transcription:
• On first run with NVIDIA GPU, you'll be offered to download CUDA libraries (~800MB)
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

Configure in: Preferences → Advanced Tab

<b>📝 Text Injection Modes</b>
Choose how text is inserted (Preferences → Advanced):
• <b>Keyboard Simulation (default):</b> Types text using ydotool/wtype
• <b>Clipboard Paste:</b> Copies to clipboard then simulates Ctrl+V
  Use this if keyboard simulation doesn't work in certain apps

<b>🎛️ Audio Settings</b>
Fine-tune audio in Preferences → Audio tab:
• Select specific microphone
• Test audio levels
• Adjust input volume (PulseAudio systems)
• Enable/disable audio beeps''')

    # Tab 5: Voice Commands
    create_tab("🗣️ Voice Commands", '''<span size="large"><b>Voice Commands Reference</b></span>

Use these spoken commands during dictation to insert punctuation and formatting.

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
• <b>literal semicolon</b> → "semicolon" (not ;)
• <b>literal colon</b> → "colon" (not :)
• <b>literal quote</b> → "quote" (not ")
• <b>literal hyphen</b> or <b>literal dash</b> → "hyphen"/"dash" (not -)
• <b>literal ellipsis</b> → "ellipsis" (not …)

Works with most voice commands!

<b>Usage Examples:</b>
Say: <i>Hello world comma how are you question mark</i>
Result: Hello world, how are you?

Say: <i>First sentence period new line Second sentence exclamation point</i>
Result: First sentence.
Second sentence!

Say: <i>The temperature is 98 point 6 degrees</i>
Result: The temperature is 98.6 degrees

Say: <i>Use the literal period command</i>
Result: Use the period command

<b>Custom Voice Commands:</b>
Define your own phrase → replacement shortcuts in Preferences → Commands tab.

Examples:
• "my email" → "user@example.com"
• "my address" → "123 Main Street, City, ST 12345"
• "signature" → "Best regards,\\nYour Name"

Custom commands are matched case-insensitively and replaced before
other processing, so you can include punctuation in replacements.

<b>Undo Commands:</b>
• Say <b>undo last word</b> to delete the last word you dictated
• Say <b>undo last sentence</b> to delete back to the previous sentence
• Say <b>undo last paragraph</b> to delete back to the last line break
• Say <b>undo everything</b> to delete ALL text from current dictation session
• Also works: <b>delete last word</b>, <b>remove last word</b>, <b>clear all</b>, etc.

<b>Smart Undo Features:</b>
• Undo only affects text that TalkType inserted (not manually typed text)
• After undoing mid-sentence, continue dictating seamlessly
  (next words will automatically be lowercase)
• Chain multiple undos to progressively remove more text

<b>Smart Features:</b>
• Auto-capitalization after sentences
• Trailing commas converted to periods before line breaks
• Auto-period added if sentence has no punctuation
• Smart quote placement and spacing''')

    # Tab 6: Tips
    create_tab("💡 Tips", '''<span size="large"><b>Tips &amp; Troubleshooting</b></span>

<b>Keyboard Shortcuts:</b>
• <b>F8:</b> Push-to-talk (hold to record, release to stop)
• <b>F9:</b> Toggle recording (press once to start, again to stop)
• Hotkeys work globally in any application
• Customize hotkeys in Preferences → General

<b>Getting Best Results:</b>
• Speak clearly at a normal pace
• Use a quality microphone for better accuracy
• Minimize background noise
• Pause briefly at sentence ends for better punctuation

<b>Audio Setup:</b>
• Use the microphone test in Preferences to check levels
• Adjust input volume if audio is too quiet or distorted
• Select the correct microphone if you have multiple inputs

<b>Status Indicators:</b>
• Tray icon shows service status (bright = running, dimmed = stopped)
• Red recording indicator appears on screen during dictation
• Audio beeps indicate recording start/stop (can be disabled)

<b>Installation &amp; Updates:</b>
• <b>AppImage location:</b> ~/AppImages/TalkType.AppImage
• <b>Desktop launcher:</b> TalkType appears in your Applications menu
• <b>Check for updates:</b> Preferences → Updates tab
• <b>Auto-update:</b> Click "Download &amp; Install" to update automatically
• Updates are downloaded, installed, and TalkType restarts seamlessly
• <b>Config files:</b> ~/.config/talktype/
• <b>AI Models:</b> ~/.cache/huggingface/

<b>Common Issues:</b>

<b>Hotkey not working:</b>
• Check if another app is using the same hotkey
• Try a different key in Preferences
• Ensure service is running

<b>Text not inserting:</b>
• Make sure cursor is in a text field
• Try switching injection mode in tray menu (Auto/Type/Paste)
• Some apps work better with Clipboard Paste mode

<b>Transcription too slow:</b>
• Enable GPU acceleration if you have NVIDIA GPU
• Try a smaller AI model (tiny/base/small)
• Use Performance presets in tray menu for quick optimization

<b>Service won't start:</b>
• Check logs: ~/.config/talktype/talktype.log
• Restart from tray menu: Stop Service then Start Service
• Ensure all dependencies are installed

<b>Pro Tips:</b>
• Enable Launch at Login to start automatically
• Use toggle mode (F9) for hands-free extended dictation
• Set auto-timeout to save battery when not in use
• Create custom voice commands for frequently-typed text''')

    # Close button
    close_button = Gtk.Button(label="Close")
    close_button.connect("clicked", lambda w: dialog.destroy())
    dialog.add_action_widget(close_button, Gtk.ResponseType.CLOSE)

    # Connect response to destroy (for non-blocking operation)
    dialog.connect("response", lambda d, r: d.destroy())

    dialog.show_all()
    dialog.present()  # Bring to front and focus

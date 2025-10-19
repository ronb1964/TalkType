"""
TalkType Help Dialog - Shared help window for tray and preferences.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


def show_help_dialog():
    """Show help dialog with TalkType features and instructions."""
    print("🔵 USING SHARED help_dialog.py - NEW CODE")  # Debug message
    from gi.repository import Gdk

    dialog = Gtk.Dialog(title="TalkType Help")
    dialog.set_default_size(650, 550)

    # Use geometry hints to force exact size
    geo = Gdk.Geometry()
    geo.min_width = 650
    geo.max_width = 650
    geo.min_height = 550
    geo.max_height = 550
    dialog.set_geometry_hints(None, geo, Gdk.WindowHints.MIN_SIZE | Gdk.WindowHints.MAX_SIZE)

    dialog.set_resizable(False)
    dialog.set_modal(True)
    dialog.set_position(Gtk.WindowPosition.CENTER)

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
• Visual recording indicator in system tray
• Audio beeps for start/stop feedback

<b>Smart Text Processing</b>
• Auto-punctuation for natural text flow
• Smart quotes (" " instead of " ")
• Auto-spacing before new text
• Optional auto-period at end of sentences

<b>Language Support</b>
• Auto-detect language from speech
• Manually select from 50+ supported languages
• Great for multilingual users

<b>Flexible Text Input</b>
• Keystroke simulation (ydotool/wtype)
• Clipboard paste mode (for apps with input issues)

<b>Audio Control</b>
• Microphone selection and testing
• Audio level monitoring
• Volume adjustment support

<b>System Integration</b>
• Launch at login option
• System tray integration
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
To prevent conversion to punctuation, say:
• <b>literal period</b> → outputs the word "period" (not .)
• <b>the word period</b> → outputs the word "period" (not .)

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

<b>Smart Features:</b>
• Auto-capitalization after sentences
• Trailing commas converted to periods before line breaks
• Auto-period added if sentence has no punctuation
• Smart quote placement and spacing''')

    # Tab 6: Tips
    create_tab("💡 Tips", '''<span size="large"><b>Tips &amp; Troubleshooting</b></span>

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
• Tray icon tooltip shows running or stopped status
• Red microphone icon appears during recording
• Audio beeps indicate recording start/stop (can be disabled)

<b>Common Issues:</b>

<b>Hotkey not working:</b>
• Check if another app is using the same hotkey
• Try a different key in Preferences
• Ensure service is running

<b>Text not inserting:</b>
• Make sure cursor is in a text field
• Try clipboard paste mode (Preferences → Advanced)
• Check if the app has special input restrictions

<b>Transcription too slow:</b>
• Enable GPU acceleration if you have NVIDIA GPU
• Try a smaller AI model (tiny/base/small)
• Check if other programs are using GPU/CPU

<b>Service won't start:</b>
• Check logs: ~/.config/talktype/talktype.log
• Restart from tray menu: Stop Service then Start Service
• Ensure all dependencies are installed

<b>Convenience Features:</b>
• Enable Launch at Login to start automatically
• Use toggle mode (F9) for hands-free extended dictation
• Set auto-timeout to save battery when not in use''')

    # Close button
    close_button = Gtk.Button(label="Close")
    close_button.connect("clicked", lambda w: dialog.destroy())
    dialog.add_action_widget(close_button, Gtk.ResponseType.CLOSE)

    dialog.show_all()
    dialog.run()
    dialog.destroy()

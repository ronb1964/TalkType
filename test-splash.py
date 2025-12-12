#!/usr/bin/env python3
"""Test splash screen icon loading."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Set up environment for system PyGObject
sys.path.insert(0, '/usr/lib64/python3.13/site-packages')
sys.path.insert(0, '/usr/lib/python3.13/site-packages')

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
import cairo
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Test icon paths
icon_paths = [
    os.path.join(os.path.dirname(__file__), "icons", "TT_retro_square_light_transparent.png"),
    "icons/TT_retro_square_light_transparent.png",
]

print("Testing icon paths:")
for path in icon_paths:
    exists = os.path.exists(path)
    print(f"  {path}: {'✓ EXISTS' if exists else '✗ NOT FOUND'}")
    if exists:
        print(f"    Size: {os.path.getsize(path)} bytes")

# Create splash window
window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
window.set_title("TalkType Splash Test")
window.set_default_size(400, 400)
window.set_position(Gtk.WindowPosition.CENTER)
window.set_decorated(False)
window.set_keep_above(True)

# Enable transparency
screen = window.get_screen()
visual = screen.get_rgba_visual()
if visual:
    window.set_visual(visual)

# Simple - no CSS styling, just let it be clean

# Create box
box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
box.set_valign(Gtk.Align.CENTER)
box.set_halign(Gtk.Align.CENTER)

# Try to load icon
icon_path = None
for path in icon_paths:
    if os.path.exists(path):
        icon_path = path
        break

if icon_path:
    print(f"\n✓ Loading icon from: {icon_path}")
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(icon_path, 256, 256)
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        box.pack_start(image, False, False, 0)
        print("✓ Icon loaded successfully")
    except Exception as e:
        print(f"✗ Error loading icon: {e}")
        label = Gtk.Label(label="TalkType")
        label.set_markup('<span size="xx-large" weight="bold">TalkType</span>')
        box.pack_start(label, False, False, 0)
else:
    print("\n✗ No icon found, using text")
    label = Gtk.Label(label="TalkType")
    label.set_markup('<span size="xx-large" weight="bold">TalkType</span>')
    box.pack_start(label, False, False, 0)

window.add(box)

# Animation state for pulsing glow
pulse_phase = [0]  # Use list to make it mutable in nested function

# Draw transparent background with blue glow using cairo
def draw_with_glow(widget, cr):
    """Draw transparent background with blue glow effect."""
    # First, paint window as transparent
    cr.set_source_rgba(0, 0, 0, 0)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.paint()

    # Get dimensions
    width = widget.get_allocated_width()
    height = widget.get_allocated_height()
    center_x = width / 2
    center_y = height / 2

    # Paint dark background with rounded corners (same color as welcome screen: #2b2b2b)
    cr.set_operator(cairo.OPERATOR_OVER)

    # Draw rounded rectangle
    radius = 15
    cr.arc(radius, radius, radius, 3.14159, 3 * 3.14159 / 2)
    cr.arc(width - radius, radius, radius, 3 * 3.14159 / 2, 0)
    cr.arc(width - radius, height - radius, radius, 0, 3.14159 / 2)
    cr.arc(radius, height - radius, radius, 3.14159 / 2, 3.14159)
    cr.close_path()

    cr.set_source_rgb(43/255, 43/255, 43/255)  # #2b2b2b
    cr.fill()

    # Now draw the blue glow on top of the dark background with expanding animation
    import math
    # Start very small near icon and expand outward over time (0.0 to 1.0)
    # This will animate from small to full size over 3 seconds
    # At 50ms per frame, 3 seconds = 60 frames, increment of 0.05 per frame
    progress = min(1.0, pulse_phase[0])  # Already increments correctly

    # Start at 80 pixels and expand to 320 pixels
    outer_radius = 80 + (240 * progress)

    gradient = cairo.RadialGradient(center_x, center_y, 60,  # inner circle (stays constant)
                                    center_x, center_y, outer_radius)  # outer circle expands

    # More color stops for softer, more gradual fade at edges
    gradient.add_color_stop_rgba(0, 66/255, 133/255, 244/255, 0.85)   # bright center
    gradient.add_color_stop_rgba(0.15, 66/255, 133/255, 244/255, 0.75)
    gradient.add_color_stop_rgba(0.3, 66/255, 133/255, 244/255, 0.6)
    gradient.add_color_stop_rgba(0.45, 66/255, 133/255, 244/255, 0.45)
    gradient.add_color_stop_rgba(0.6, 66/255, 133/255, 244/255, 0.3)
    gradient.add_color_stop_rgba(0.75, 66/255, 133/255, 244/255, 0.15)
    gradient.add_color_stop_rgba(0.88, 66/255, 133/255, 244/255, 0.05)
    gradient.add_color_stop_rgba(1, 66/255, 133/255, 244/255, 0.0)    # very soft fade to transparent

    cr.set_source(gradient)
    cr.paint()

    # Let GTK draw the rest (the icon)
    return False

window.connect("draw", draw_with_glow)
window.set_app_paintable(True)  # Let us control all painting
window.show_all()

# Animate the pulsing glow
fade_alpha = [1.0]  # For fade out effect

def animate_pulse():
    """Update pulse phase for smooth animation."""
    pulse_phase[0] += 0.042  # Slightly slower - will reach 1.0 in about 3.2 seconds
    window.queue_draw()  # Trigger redraw
    return True  # Keep timer running

GLib.timeout_add(50, animate_pulse)  # Update every 50ms for smooth animation

# Welcome dialog reference for overlapping transition
welcome_dialog_ref = [None]
welcome_fade_started = [False]

# Fade out the splash window
def fade_out():
    """Gradually fade out the splash window with smooth transition."""
    fade_alpha[0] -= 0.07  # Even quicker fade for splash
    window.set_opacity(fade_alpha[0])

    # Start welcome fade-in when splash is 50% faded (overlap transition)
    if fade_alpha[0] <= 0.5 and not welcome_fade_started[0]:
        welcome_fade_started[0] = True

        # Show the welcome dialog and start fading it in
        from talktype.welcome_dialog import WelcomeDialog
        dialog = WelcomeDialog(force_gnome=True, force_nvidia=True)
        welcome_dialog_ref[0] = dialog

        # Start welcome dialog invisible and fade it in
        dialog.dialog.set_opacity(0)
        dialog.dialog.show_all()

        welcome_alpha = [0.0]
        def fade_in_welcome():
            welcome_alpha[0] += 0.06  # Quicker fade-in for welcome
            dialog.dialog.set_opacity(welcome_alpha[0])
            if welcome_alpha[0] >= 1.0:
                return False  # Stop fading
            return True

        GLib.timeout_add(15, fade_in_welcome)  # Fade in over ~250ms

    if fade_alpha[0] <= 0:
        # Splash fade complete, destroy splash window
        window.destroy()

        # Run the welcome dialog
        result = welcome_dialog_ref[0].run()
        welcome_dialog_ref[0].destroy()

        print(f"\nWelcome dialog result: {result}")
        Gtk.main_quit()
        return False

    return True  # Keep fading

# Start fade after glow completes (about 3.3 seconds)
def start_fade():
    GLib.timeout_add(20, fade_out)  # Fade out over ~400ms
    return False

GLib.timeout_add(3300, start_fade)  # Start fade shortly after glow completes

# Also allow manual close
def close_window(widget=None, event=None):
    Gtk.main_quit()
    return False

window.connect("delete-event", close_window)

print("\nShowing splash window (will auto-transition to welcome dialog after 3 seconds)...")
Gtk.main()

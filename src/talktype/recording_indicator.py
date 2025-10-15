#!/usr/bin/env python3
"""
Visual recording indicator for TalkType
Shows an animated orb with satellites near the cursor during dictation
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import cairo
import math
import time


class RecordingIndicator(Gtk.Window):
    """Floating recording indicator window with configurable position"""

    def __init__(self, position="center", offset_x=0, offset_y=0, size="medium"):
        super().__init__(title="TalkType Recording")

        # Position configuration
        self.position = position.lower()
        self.offset_x = offset_x
        self.offset_y = offset_y

        # Size scaling: small=0.6, medium=1.0, large=1.4
        size_scales = {"small": 0.6, "medium": 1.0, "large": 1.4}
        self.scale = size_scales.get(size.lower(), 1.0)

        # Window setup - transparent, always on top, no decorations
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_accept_focus(False)
        self.set_can_focus(False)
        self.set_focus_on_map(False)
        self.set_type_hint(Gdk.WindowTypeHint.TOOLTIP)  # Changed from NOTIFICATION to TOOLTIP
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_default_size(200, 100)  # Increased size to prevent clipping

        # Try to allow positioning (may not work on all compositors)
        self.set_position(Gtk.WindowPosition.NONE)

        # Make window support transparency
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # Animation state
        self.start_time = time.time()
        self.pulse_phase = 0.0  # For pulsing animation
        self.base_size = int(15 * self.scale)  # Base orb radius (scaled)
        self.particle_pulse_phase = 0.0  # For individual particle pulsing
        self.is_recording = False
        self.audio_level = 0.0  # Real-time audio level (0-1)

        # Drawing area
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.connect('draw', self.on_draw)
        self.add(self.drawing_area)

        # Animation timer (60 FPS)
        self.animation_timeout_id = None

        self.set_app_paintable(True)

    def show_at_position(self):
        """Show the indicator at the configured position"""
        # Must be called from GTK main thread
        def _do_show():
            try:
                # Get screen dimensions
                screen = self.get_screen()
                screen_width = screen.get_width()
                screen_height = screen.get_height()

                # Window dimensions (scaled)
                window_width = int(200 * self.scale)
                window_height = int(100 * self.scale)

                # Calculate base position based on configured anchor
                if self.position == "center":
                    window_x = (screen_width - window_width) // 2
                    window_y = (screen_height - window_height) // 2
                elif self.position == "top-left":
                    window_x = 20
                    window_y = 20
                elif self.position == "top-center":
                    window_x = (screen_width - window_width) // 2
                    window_y = 20
                elif self.position == "top-right":
                    window_x = screen_width - window_width - 20
                    window_y = 20
                elif self.position == "bottom-left":
                    window_x = 20
                    window_y = screen_height - window_height - 20
                elif self.position == "bottom-center":
                    window_x = (screen_width - window_width) // 2
                    window_y = screen_height - window_height - 20
                elif self.position == "bottom-right":
                    window_x = screen_width - window_width - 20
                    window_y = screen_height - window_height - 20
                elif self.position == "left-center":
                    window_x = 20
                    window_y = (screen_height - window_height) // 2
                elif self.position == "right-center":
                    window_x = screen_width - window_width - 20
                    window_y = (screen_height - window_height) // 2
                else:
                    # Default to center if position unknown
                    window_x = (screen_width - window_width) // 2
                    window_y = (screen_height - window_height) // 2

                # Apply custom offset
                window_x += self.offset_x
                window_y += self.offset_y

                # Ensure window stays on screen
                window_x = max(0, min(window_x, screen_width - window_width))
                window_y = max(0, min(window_y, screen_height - window_height))

                # Make window completely pass-through for input events
                # This prevents it from interfering with keyboard/mouse input
                self.set_accept_focus(False)
                self.input_shape_combine_region(None)  # Pass all input through

                self.show_all()
                # Don't call present() - it might steal focus from the text entry field

                # Move AFTER showing (Wayland may ignore this, but try anyway)
                self.move(window_x, window_y)

                # Try moving again after a tiny delay to work around compositor repositioning
                def try_move_again():
                    self.move(window_x, window_y)
                    return False
                GLib.timeout_add(50, try_move_again)

                # Start animation
                self.start_time = time.time()
                if self.animation_timeout_id is None:
                    self.animation_timeout_id = GLib.timeout_add(16, self.update_animation)
            except Exception as e:
                print(f"❌ Error showing indicator: {e}")
                import traceback
                traceback.print_exc()
            return False  # Don't repeat

        GLib.idle_add(_do_show)

    def hide_indicator(self):
        """Hide the indicator and stop animation"""
        def _do_hide():
            self.hide()
            if self.animation_timeout_id is not None:
                GLib.source_remove(self.animation_timeout_id)
                self.animation_timeout_id = None
            self.is_recording = False
            self.audio_level = 0.0
            return False

        GLib.idle_add(_do_hide)

    def start_recording(self):
        """Start recording mode"""
        self.is_recording = True
        self.start_time = time.time()

    def stop_recording(self):
        """Stop recording mode"""
        self.is_recording = False
        self.audio_level = 0.0

    def set_audio_level(self, level: float):
        """Update the audio level for satellite animation (0.0 - 1.0)"""
        self.audio_level = max(0.0, min(1.0, level))

    def update_animation(self):
        """Update animation state"""
        if self.is_recording:
            # When recording: orb is frozen, satellites move with audio
            pass  # audio_level is updated externally
        else:
            # At rest mode: orb pulsates, particles stay stationary
            self.pulse_phase = (self.pulse_phase + 0.05) % (2 * math.pi)
            self.particle_pulse_phase = (self.particle_pulse_phase + 0.03) % (2 * math.pi)

        # Trigger redraw
        self.drawing_area.queue_draw()
        return True

    def on_draw(self, widget, cr):
        """Draw the indicator"""
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()

        # Clear with full transparency
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        # Calculate orb position (center-left area)
        orb_x = width * 0.3
        orb_y = height * 0.5

        # Draw pill-shaped background container
        self.draw_pill_background(cr, orb_x, orb_y)

        # Draw the animated orb
        self.draw_orb(cr, orb_x, orb_y)

        # Draw timer aligned with orb center (scaled position)
        elapsed = int(time.time() - self.start_time)
        self.draw_timer(cr, orb_x + 32 * self.scale, orb_y, elapsed)

    def draw_pill_background(self, cr, orb_x, orb_y):
        """Draw semi-transparent pill-shaped background"""
        # Pill dimensions - scaled
        pill_width = 130 * self.scale
        pill_height = 55 * self.scale
        pill_radius = pill_height / 2
        pill_x = orb_x - 32 * self.scale
        pill_y = orb_y - pill_height / 2

        # Draw rounded rectangle (pill shape)
        cr.new_sub_path()
        cr.arc(pill_x + pill_radius, pill_y + pill_radius, pill_radius, math.pi, 3 * math.pi / 2)
        cr.arc(pill_x + pill_width - pill_radius, pill_y + pill_radius, pill_radius, 3 * math.pi / 2, 0)
        cr.arc(pill_x + pill_width - pill_radius, pill_y + pill_height - pill_radius, pill_radius, 0, math.pi / 2)
        cr.arc(pill_x + pill_radius, pill_y + pill_height - pill_radius, pill_radius, math.pi / 2, math.pi)
        cr.close_path()

        # Semi-transparent dark background - more opaque
        cr.set_source_rgba(0.1, 0.1, 0.15, 0.85)
        cr.fill()

        # Red border when recording (push-to-talk active)
        if self.is_recording:
            cr.new_sub_path()
            cr.arc(pill_x + pill_radius, pill_y + pill_radius, pill_radius, math.pi, 3 * math.pi / 2)
            cr.arc(pill_x + pill_width - pill_radius, pill_y + pill_radius, pill_radius, 3 * math.pi / 2, 0)
            cr.arc(pill_x + pill_width - pill_radius, pill_y + pill_height - pill_radius, pill_radius, 0, math.pi / 2)
            cr.arc(pill_x + pill_radius, pill_y + pill_height - pill_radius, pill_radius, math.pi / 2, math.pi)
            cr.close_path()
            cr.set_source_rgba(1.0, 0.2, 0.2, 0.9)  # Bright red
            cr.set_line_width(2.5 * self.scale)
            cr.stroke()

    def draw_orb(self, cr, x, y):
        """Draw the glowing orb with pulsing animation"""
        # Calculate current size based on gentle pulse (only when not recording)
        if self.is_recording:
            # Freeze the pulse when recording - keep orb steady
            current_size = self.base_size
        else:
            # Gentle pulse animation when at rest
            pulse_scale = 1.0 + 0.1 * math.sin(self.pulse_phase)
            current_size = self.base_size * pulse_scale

        # Outer glow layers (multiple for softer effect)
        glow_color = (0.3, 0.7, 1.0)  # Cyan

        for i in range(3):
            glow_radius = current_size * (1.5 - i * 0.15)
            gradient = cairo.RadialGradient(x, y, current_size * 0.5, x, y, glow_radius)

            alpha = 0.4 * (1.0 - i * 0.3) if not self.is_recording else 0.4 * self.audio_level * (1.0 - i * 0.3)
            gradient.add_color_stop_rgba(0, glow_color[0], glow_color[1], glow_color[2], alpha)
            gradient.add_color_stop_rgba(1, glow_color[0], glow_color[1], glow_color[2], 0)

            cr.set_source(gradient)
            cr.arc(x, y, glow_radius, 0, 2 * math.pi)
            cr.fill()

        # Core orb with soft, hazy edge
        core_gradient = cairo.RadialGradient(x, y, 0, x, y, current_size * 1.3)
        core_gradient.add_color_stop_rgba(0, 1.0, 1.0, 1.0, 1.0)  # White center
        core_gradient.add_color_stop_rgba(0.4, 0.5, 0.9, 1.0, 0.9)  # Light cyan
        core_gradient.add_color_stop_rgba(0.7, 0.2, 0.6, 0.9, 0.6)  # Blue mid
        core_gradient.add_color_stop_rgba(0.9, 0.2, 0.5, 0.8, 0.3)  # Soft edge
        core_gradient.add_color_stop_rgba(1.0, 0.2, 0.5, 0.8, 0.0)  # Fade to transparent

        cr.set_source(core_gradient)
        cr.arc(x, y, current_size * 1.3, 0, 2 * math.pi)
        cr.fill()

        # Particles around orb - use fixed base_size, not pulsing current_size
        self.draw_particles(cr, x, y, self.base_size * 1.8)

    def draw_particles(self, cr, center_x, center_y, base_radius):
        """Draw small glowing particles that extend radially based on voice"""
        num_particles = 16

        for i in range(num_particles):
            # Fixed angle for each particle (evenly distributed around circle)
            angle = i * 2 * math.pi / num_particles

            # Radial distance: start touching orb, limited extension
            # Quiet/Silence (0.0): 0.7x base radius (very close, almost touching)
            # Loud (1.0): 1.4x base radius (reduced from 1.7 for more compact look)
            min_distance = 0.7
            max_distance = 1.4

            if self.is_recording:
                # Move radially based on audio level
                particle_radial_extend = self.audio_level
            else:
                # Stay at rest position
                particle_radial_extend = 0.0

            radial_distance = base_radius * (min_distance + (max_distance - min_distance) * particle_radial_extend)

            # Particle position along the radial line
            px = center_x + radial_distance * math.cos(angle)
            py = center_y + radial_distance * math.sin(angle)

            # Particle size: subtle pulse at rest, or responds to voice when active
            if self.is_recording:
                # Size varies with voice level
                particle_size = 4 + (self.audio_level * 2)
            else:
                # Subtle individual pulse at rest (each particle slightly offset)
                individual_offset = i * 0.4  # Stagger the pulse per particle
                pulse = 1.0 + 0.15 * math.sin(self.particle_pulse_phase + individual_offset)
                particle_size = 4 * pulse

            # Color shifts based on distance from orb
            # Close to orb: warm cyan/white (0.7, 0.95, 1.0)
            # Far from orb: cooler blue/purple (0.4, 0.6, 1.0)
            distance_factor = (radial_distance / base_radius - min_distance) / (max_distance - min_distance)
            r = 0.7 - (distance_factor * 0.3)  # 0.7 -> 0.4
            g = 0.95 - (distance_factor * 0.35)  # 0.95 -> 0.6
            b = 1.0  # Always full blue

            # Particle glow (brighter when more energetic)
            alpha = 0.6 + (self.audio_level * 0.3) if self.is_recording else 0.6
            particle_gradient = cairo.RadialGradient(px, py, 0, px, py, particle_size * 1.5)
            particle_gradient.add_color_stop_rgba(0, r, g, b, alpha)
            particle_gradient.add_color_stop_rgba(1, r * 0.7, g * 0.7, b, 0)

            cr.set_source(particle_gradient)
            cr.arc(px, py, particle_size * 1.5, 0, 2 * math.pi)
            cr.fill()

    def draw_timer(self, cr, x, y, seconds):
        """Draw the timer text centered vertically with orb"""
        # Format time as MM:SS
        minutes = seconds // 60
        secs = seconds % 60
        time_text = f"{minutes}:{secs:02d}"

        # Set font - scaled
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(22 * self.scale)

        # Get text extents for vertical centering
        extents = cr.text_extents(time_text)
        text_height = extents.height
        text_y = y + text_height / 2

        # Draw shadow for readability (scaled offset)
        cr.set_source_rgba(0, 0, 0, 0.5)
        cr.move_to(x + 2 * self.scale, text_y + 2 * self.scale)
        cr.show_text(time_text)

        # Draw main text
        cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.move_to(x, text_y)
        cr.show_text(time_text)

#!/usr/bin/env python3
"""
Visual demo of the recording indicator orb
Standalone window to preview the animation before integration
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import cairo
import math
import time
import numpy as np
import threading
import sounddevice as sd

class OrbDemo(Gtk.Window):
    def __init__(self):
        super().__init__(title="Recording Orb Demo")

        # Window setup
        self.set_default_size(400, 300)
        self.set_decorated(True)  # Keep decorations for demo

        # Make window support transparency
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # Animation state
        self.start_time = time.time()
        self.pulse_phase = 0.0  # For pulsing animation
        self.base_size = 15  # Base orb radius (scaled down)
        self.glow_intensity = 0.0  # Simulated voice level (0-1)
        self.particle_radial_extend = 0.0  # How far particles extend outward (0-1)
        self.particle_pulse_phase = 0.0  # For individual particle pulsing
        self.use_real_audio = False  # Toggle with F10
        self.audio_level = 0.0  # Real-time audio level from mic
        self.is_recording = False

        # Audio setup
        self.audio_thread = None
        self.running = True

        # Drawing area
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.connect('draw', self.on_draw)
        self.add(self.drawing_area)

        # Animation timer (60 FPS)
        GLib.timeout_add(16, self.update_animation)

        # Instructions label
        self.set_app_paintable(True)

        # Keyboard event handler
        self.connect("key-press-event", self.on_key_press)
        self.connect("key-release-event", self.on_key_release)
        self.connect("destroy", self.on_destroy)

    def on_key_press(self, widget, event):
        """Handle keyboard events"""
        if event.keyval == Gdk.KEY_F10:
            if not self.use_real_audio:
                self.start_audio_input()
        return True

    def on_key_release(self, widget, event):
        """Handle key release events"""
        if event.keyval == Gdk.KEY_F10:
            if self.use_real_audio:
                self.stop_audio_input()
        return True

    def on_destroy(self, widget):
        """Clean up when window is closed"""
        self.running = False
        self.stop_audio_input()

    def start_audio_input(self):
        """Start listening to microphone (push-to-talk)"""
        self.use_real_audio = True
        self.is_recording = True
        self.audio_level = 0.0  # Reset audio level
        if self.audio_thread is None or not self.audio_thread.is_alive():
            self.audio_thread = threading.Thread(target=self.audio_monitor_thread, daemon=True)
            self.audio_thread.start()
        print("Listening to microphone - speak now!")

    def stop_audio_input(self):
        """Stop listening to microphone"""
        self.use_real_audio = False
        self.is_recording = False
        self.audio_level = 0.0  # Reset to zero so particles return to rest
        print("Stopped listening")

    def audio_monitor_thread(self):
        """Background thread to monitor audio levels"""
        def audio_callback(indata, frames, time_info, status):
            """Callback for audio stream"""
            if status:
                print(f"Audio status: {status}")

            # Calculate RMS (root mean square) for audio level
            rms = np.sqrt(np.mean(indata**2))

            # Normalize to 0-1 range (moderate sensitivity to avoid pegging)
            # Lower multiplier so background noise doesn't push particles out
            normalized = min(1.0, max(0.0, rms * 20.0))

            # Smooth but responsive
            self.audio_level = self.audio_level * 0.4 + normalized * 0.6

        try:
            with sd.InputStream(
                channels=1,
                samplerate=16000,
                blocksize=1024,
                callback=audio_callback
            ):
                while self.use_real_audio and self.running:
                    sd.sleep(100)

        except Exception as e:
            print(f"Audio error: {e}")

    def update_animation(self):
        """Update animation state"""
        current_time = time.time() - self.start_time

        # Use real audio or simulated voice level
        if self.use_real_audio:
            # When using real audio, freeze the orb pulse and only respond to voice
            self.glow_intensity = self.audio_level
            # Particles move radially based on voice
            self.particle_radial_extend = self.audio_level
            # Don't animate orb pulse during voice input
        else:
            # At rest mode: orb pulsates, particles stay stationary
            # Pulse phase (smooth sine wave for core orb - constant gentle pulse)
            self.pulse_phase = (self.pulse_phase + 0.05) % (2 * math.pi)
            # Particle individual pulse (very subtle)
            self.particle_pulse_phase = (self.particle_pulse_phase + 0.03) % (2 * math.pi)
            # Particles don't move radially at rest - stay at minimum position
            self.particle_radial_extend = 0.0

        # Trigger redraw
        self.drawing_area.queue_draw()
        return True

    def on_draw(self, widget, cr):
        """Draw the orb and timer"""
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()

        # Clear with transparent background
        cr.set_source_rgba(0.1, 0.1, 0.1, 0.3)  # Dark semi-transparent for demo
        cr.paint()

        # Calculate orb position (center-left area)
        orb_x = width * 0.3
        orb_y = height * 0.5

        # Draw pill-shaped background container
        self.draw_pill_background(cr, orb_x, orb_y)

        # Draw the animated orb
        self.draw_orb(cr, orb_x, orb_y)

        # Draw timer aligned with orb center
        elapsed = int(time.time() - self.start_time)
        self.draw_timer(cr, orb_x + 32, orb_y, elapsed)

    def draw_pill_background(self, cr, orb_x, orb_y):
        """Draw semi-transparent pill-shaped background"""
        # Pill dimensions - scaled down proportionally
        pill_width = 130  # Narrower
        pill_height = 55  # Shorter
        pill_radius = pill_height / 2
        pill_x = orb_x - 32
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
        if self.use_real_audio:
            cr.new_sub_path()
            cr.arc(pill_x + pill_radius, pill_y + pill_radius, pill_radius, math.pi, 3 * math.pi / 2)
            cr.arc(pill_x + pill_width - pill_radius, pill_y + pill_radius, pill_radius, 3 * math.pi / 2, 0)
            cr.arc(pill_x + pill_width - pill_radius, pill_y + pill_height - pill_radius, pill_radius, 0, math.pi / 2)
            cr.arc(pill_x + pill_radius, pill_y + pill_height - pill_radius, pill_radius, math.pi / 2, math.pi)
            cr.close_path()
            cr.set_source_rgba(1.0, 0.2, 0.2, 0.9)  # Bright red
            cr.set_line_width(2.5)
            cr.stroke()

    def draw_orb(self, cr, x, y):
        """Draw the glowing orb with pulsing animation"""
        # Calculate current size based on gentle pulse (only when not using real audio)
        if self.use_real_audio:
            # Freeze the pulse when using real audio - keep orb steady
            current_size = self.base_size
        else:
            # Gentle pulse animation when simulating
            pulse_scale = 1.0 + 0.1 * math.sin(self.pulse_phase)
            current_size = self.base_size * pulse_scale

        # Outer glow layers (multiple for softer effect)
        glow_color = (0.3, 0.7, 1.0)  # Cyan

        for i in range(3):
            glow_radius = current_size * (1.5 - i * 0.15)
            gradient = cairo.RadialGradient(x, y, current_size * 0.5, x, y, glow_radius)

            alpha = 0.4 * self.glow_intensity * (1.0 - i * 0.3)
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
            radial_distance = base_radius * (min_distance + (max_distance - min_distance) * self.particle_radial_extend)

            # Particle position along the radial line
            px = center_x + radial_distance * math.cos(angle)
            py = center_y + radial_distance * math.sin(angle)

            # Particle size: subtle pulse at rest, or responds to voice when active
            if self.use_real_audio:
                # Size varies with voice level
                particle_size = 4 + (self.glow_intensity * 2)
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
            alpha = 0.6 + (self.glow_intensity * 0.3)
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

        # Set font - smaller
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(22)

        # Get text extents for vertical centering
        extents = cr.text_extents(time_text)
        text_height = extents.height
        text_y = y + text_height / 2

        # Draw shadow for readability
        cr.set_source_rgba(0, 0, 0, 0.5)
        cr.move_to(x + 2, text_y + 2)
        cr.show_text(time_text)

        # Draw main text
        cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.move_to(x, text_y)
        cr.show_text(time_text)

def main():
    win = OrbDemo()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()

    print("Recording Orb Demo")
    print("=" * 50)
    print("HOLD F10 for push-to-talk (release to stop)")
    print("Speak while holding F10 to see particles react!")
    print("Orb freezes when listening, particles move with your voice.")
    print("Close window when done reviewing.")
    print("=" * 50)

    Gtk.main()

if __name__ == '__main__':
    main()

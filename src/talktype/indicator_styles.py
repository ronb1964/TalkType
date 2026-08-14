"""Cairo drawing for the recording indicator's new styles + the soft backing.

Pure cairo (no GTK widget), so every renderer is testable by drawing onto an
ImageSurface with no display. Geometry and colors were settled by live
prototyping with Ron; see
docs/superpowers/specs/2026-08-14-recording-indicator-styles-design.md.
"""
import math

import cairo

# Core alpha of the soft dark backing, per level. Approved by Ron.
BACKING_LEVELS = {"off": 0.0, "soft": 0.34, "medium": 0.50, "strong": 0.68}


def resolve_color(mode, custom_hex, accent_rgb):
    """(r,g,b) in 0..1 for the active color mode."""
    if mode == "custom":
        h = custom_hex.lstrip("#")
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return tuple(accent_rgb)


def _fg(base, intensity, alpha=None):
    """Foreground color, brightened slightly toward white with intensity."""
    t = 0.35 * intensity
    rgb = tuple(base[i] + (1.0 - base[i]) * t for i in range(3))
    return (*rgb, alpha if alpha is not None else 0.82 + 0.18 * intensity)


def backing_alpha(r, core, plateau=0.42):
    """Alpha of the backing at normalized radius r (0=center, 1=edge).

    Flat `core` out to `plateau`, then a raised-cosine taper to zero. The
    cosine lands at r=1 with zero slope, so the backing dissolves instead of
    ending in a hard outline.
    """
    if core <= 0.0:
        return 0.0
    if r <= plateau:
        return core
    t = (r - plateau) / (1.0 - plateau)
    return core * (0.5 + 0.5 * math.cos(math.pi * t))


def draw_backing(cr, cx, cy, rx, ry, core):
    """Feathered dark backing centered at (cx,cy), sized rx×ry.

    Sampled across many stops because cairo draws straight lines between stops,
    and too few showed each junction as a faint ring. rx/ry must be chosen so
    the ellipse feathers to zero inside the window, or the window clips it into
    a hard edge.
    """
    if core <= 0.001:
        return
    cr.save()
    cr.translate(cx, cy)
    cr.scale(rx, ry)
    g = cairo.RadialGradient(0, 0, 0, 0, 0, 1)
    N = 96
    for k in range(N + 1):
        r = k / N
        g.add_color_stop_rgba(r, 0.05, 0.06, 0.09, backing_alpha(r, core))
    cr.set_source(g)
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.fill()
    cr.restore()


def draw_waveform(cr, w, h, samples, level, color_rgb, backing_core, sensitivity):
    draw_backing(cr, w / 2, h / 2, w * 0.48, h * 0.44, backing_core)
    if len(samples) == 0:
        return
    iw = w * 0.60
    x0 = (w - iw) / 2
    mid = h / 2
    amp = (h * 0.46 / 2) * 0.9
    n = max(1, int(iw))
    step = max(1, len(samples) // n)
    pts = samples[::step][:n]
    cr.new_path()
    for i, v in enumerate(pts):
        y = mid - max(-1.0, min(1.0, v * 3.0 * sensitivity)) * amp
        cr.line_to(x0 + i, y) if i else cr.move_to(x0 + i, y)
    cr.set_source_rgba(*_fg(color_rgb, min(1.0, level + 0.3)))
    cr.set_line_width(2.6)
    cr.stroke()


def draw_bars(cr, w, h, spectrum, color_rgb, backing_core):
    draw_backing(cr, w / 2, h / 2, w * 0.49, h * 0.46, backing_core)
    n = len(spectrum)
    if n == 0:
        return
    iw = w * 0.52
    x0 = (w - iw) / 2
    gap = 4
    bw = (iw - gap * (n - 1)) / n
    ch = h * 0.40
    baseline = h / 2 + ch / 2
    for i, mag in enumerate(spectrum):
        x = x0 + i * (bw + gap)
        bh = max(2, mag * ch)
        cr.set_source_rgba(*_fg(color_rgb, mag, alpha=0.64 + 0.36 * mag))
        cr.rectangle(x, baseline - bh, bw, bh)
        cr.fill()


def draw_radial(cr, w, h, samples, level, color_rgb, backing_core, sensitivity):
    cx, cy = w / 2, h / 2
    max_r = min(w, h) * 0.22
    draw_backing(cr, cx, cy, max_r + 46, max_r + 46, backing_core)
    if len(samples) == 0:
        return
    base = max_r * 0.34
    n = 96
    step = max(1, len(samples) // n)
    pts = samples[::step][:n]
    cr.new_path()
    for i, v in enumerate(pts):
        ang = (i / len(pts)) * 2 * math.pi
        rr = base + max(-1.0, min(1.0, v * sensitivity)) * (max_r - base) * 0.9 + level * 4
        rr = min(rr, max_r)
        x, y = cx + math.cos(ang) * rr, cy + math.sin(ang) * rr
        cr.line_to(x, y) if i else cr.move_to(x, y)
    cr.close_path()
    cr.set_source_rgba(*_fg(color_rgb, min(1.0, level + 0.3)))
    cr.set_line_width(2.6)
    cr.stroke()
    cr.set_source_rgba(*_fg(color_rgb, level, 0.8))
    cr.arc(cx, cy, base * 0.7 + level * 5, 0, 2 * math.pi)
    cr.fill()

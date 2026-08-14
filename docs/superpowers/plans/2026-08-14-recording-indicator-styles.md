# Recording Indicator Styles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three selectable recording-indicator styles (waveform, frequency bars, radial) alongside the existing orb, each color-selectable and drawn over a soft feathered backing, with a sensitivity control — all applying live with no service restart.

**Architecture:** Pure-numpy DSP (`indicator_dsp.py`) and pure-cairo drawing (`indicator_styles.py`) are separated from the GTK widget so both are unit-testable without a display. `RecordingIndicator` gains a `style` dispatch, data setters, and color/backing/sensitivity attributes; its orb code path is untouched. `app.py`'s audio callback computes only what the active style needs and feeds it. New config keys ride the existing `LIVE_APPLIED_KEYS` live-apply mechanism.

**Tech Stack:** Python 3, numpy (FFT + DSP), pycairo (drawing), GTK3/PyGObject (widget + Preferences), pytest.

## Global Constraints

- Run tests with: `PYTHONPATH=/home/ron/Projects/TalkType/src:/usr/lib64/python3.14/site-packages:/usr/lib/python3.14/site-packages .venv/bin/python -m pytest tests/ -q`
- User-facing text uses American spelling: **"Color"**, never "Colour".
- The orb style must render identically to today — do not touch its draw path (`draw_orb`, `draw_particles`, `draw_pill_background`, `draw_timer`).
- Never set `GDK_BACKEND` globally (see `tests/test_gdk_backend_scope.py`).
- Every new `Settings` field must be classified into `LIVE_APPLIED_KEYS` or `RESTART_REQUIRED_KEYS` — `tests/test_live_settings.py::TestSettingsCoverage` enforces total coverage.
- Approved defaults: style `orb`; new-style color mode `system`; backing `medium`; sensitivity `1.0`; orb stays original cyan unless `orb_follow_system_color` is set.

---

### Task 1: Config keys, validation, and live-apply classification

**Files:**
- Modify: `src/talktype/config.py` (Settings dataclass ~line 84; VALID_* sets ~line 74; validate_settings ~line 175; LIVE_APPLIED_KEYS ~line 572)
- Test: `tests/test_indicator_config.py`

**Interfaces:**
- Produces: `Settings.indicator_style: str`, `Settings.indicator_color_mode: str`, `Settings.indicator_color: str`, `Settings.indicator_backing: str`, `Settings.indicator_sensitivity: float`, `Settings.orb_follow_system_color: bool`; module constants `VALID_INDICATOR_STYLES`, `VALID_COLOR_MODES`, `VALID_BACKINGS`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_indicator_config.py
from talktype import config


def test_new_indicator_fields_have_approved_defaults():
    s = config.Settings()
    assert s.indicator_style == "orb"
    assert s.indicator_color_mode == "system"
    assert s.indicator_backing == "medium"
    assert s.indicator_sensitivity == 1.0
    assert s.orb_follow_system_color is False


def test_valid_sets_exist():
    assert config.VALID_INDICATOR_STYLES == {"orb", "waveform", "bars", "radial"}
    assert config.VALID_COLOR_MODES == {"system", "custom"}
    assert config.VALID_BACKINGS == {"off", "soft", "medium", "strong"}


def test_new_keys_are_live_applied_not_restart():
    keys = {"indicator_style", "indicator_color_mode", "indicator_color",
            "indicator_backing", "indicator_sensitivity", "orb_follow_system_color"}
    assert keys <= config.LIVE_APPLIED_KEYS
    assert not (keys & config.RESTART_REQUIRED_KEYS)


def test_invalid_style_is_reported():
    s = config.Settings()
    s.indicator_style = "bogus"
    problems = dict(config.validate_settings(s))
    assert "indicator_style" in problems


def test_sensitivity_out_of_range_is_reported():
    s = config.Settings()
    s.indicator_sensitivity = 9.0
    problems = dict(config.validate_settings(s))
    assert "indicator_sensitivity" in problems
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... -m pytest tests/test_indicator_config.py -q`
Expected: FAIL (AttributeError / missing constants).

- [ ] **Step 3: Add the constants near the other VALID_* sets**

```python
# config.py, near VALID_INDICATOR_POSITIONS
VALID_INDICATOR_STYLES = {"orb", "waveform", "bars", "radial"}
VALID_COLOR_MODES = {"system", "custom"}
VALID_BACKINGS = {"off", "soft", "medium", "strong"}
```

- [ ] **Step 4: Add the fields to the Settings dataclass**

```python
# config.py, in the Settings dataclass, near the other indicator_* fields
    indicator_style: str = "orb"               # orb / waveform / bars / radial
    indicator_color_mode: str = "system"       # system / custom (new styles)
    indicator_color: str = "#48b7f5"           # custom color, used when mode=custom
    indicator_backing: str = "medium"          # off / soft / medium / strong
    indicator_sensitivity: float = 1.0         # scales audio-reactive amplitude
    orb_follow_system_color: bool = False      # orb uses accent instead of cyan
```

- [ ] **Step 5: Add validation in validate_settings**

```python
# config.py, inside validate_settings(s), near the indicator_position check
    if s.indicator_style.lower() not in VALID_INDICATOR_STYLES:
        problems.append(("indicator_style",
            f"Invalid indicator_style '{s.indicator_style}'. Valid: {', '.join(sorted(VALID_INDICATOR_STYLES))}"))
    if s.indicator_color_mode.lower() not in VALID_COLOR_MODES:
        problems.append(("indicator_color_mode",
            f"Invalid indicator_color_mode '{s.indicator_color_mode}'. Valid: {', '.join(sorted(VALID_COLOR_MODES))}"))
    if s.indicator_backing.lower() not in VALID_BACKINGS:
        problems.append(("indicator_backing",
            f"Invalid indicator_backing '{s.indicator_backing}'. Valid: {', '.join(sorted(VALID_BACKINGS))}"))
    if not (0.5 <= s.indicator_sensitivity <= 2.0):
        problems.append(("indicator_sensitivity",
            f"Invalid indicator_sensitivity '{s.indicator_sensitivity}'. Must be between 0.5 and 2.0"))
```

- [ ] **Step 6: Add all six keys to LIVE_APPLIED_KEYS**

```python
# config.py, add to the LIVE_APPLIED_KEYS set literal
    "indicator_style",
    "indicator_color_mode",
    "indicator_color",
    "indicator_backing",
    "indicator_sensitivity",
    "orb_follow_system_color",
```

- [ ] **Step 7: Run tests to verify pass (including the coverage test)**

Run: `... -m pytest tests/test_indicator_config.py tests/test_live_settings.py -q`
Expected: PASS (coverage test confirms every new field is classified).

- [ ] **Step 8: Commit**

```bash
git add src/talktype/config.py tests/test_indicator_config.py
git commit -m "Add recording-indicator style/color/backing/sensitivity config keys"
```

---

### Task 2: Spectrum DSP with per-band background subtraction

**Files:**
- Create: `src/talktype/indicator_dsp.py`
- Test: `tests/test_indicator_dsp.py`

**Interfaces:**
- Produces: `SpectrumProcessor(sample_rate=16000, ring_size=5600, bins=20, freq_lo=110, freq_hi=4200)` with `.process(samples: np.ndarray) -> np.ndarray` returning `bins` floats in 0..1.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_indicator_dsp.py
import numpy as np
from talktype.indicator_dsp import SpectrumProcessor

SR = 16000


def _tone(freq, n, amp=0.3):
    t = np.arange(n) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_output_shape_and_range():
    sp = SpectrumProcessor(sample_rate=SR, bins=20)
    out = sp.process(_tone(1000, 1600))
    assert out.shape == (20,)
    assert np.all(out >= 0.0) and np.all(out <= 1.0)


def test_steady_tone_is_subtracted_to_near_zero():
    """A constant tone is learned as baseline and fades out."""
    sp = SpectrumProcessor(sample_rate=SR, bins=20)
    tone = _tone(1000, 1600)
    last = None
    for _ in range(400):          # feed the same tone many times
        last = sp.process(tone)
    assert last.max() < 0.15, "a steady tone should decay toward zero"


def test_silence_is_zero():
    sp = SpectrumProcessor(sample_rate=SR, bins=20)
    out = sp.process(np.zeros(1600, dtype=np.float32))
    assert out.max() < 1e-6


def test_dc_offset_does_not_pin_the_low_band():
    """A large DC offset must be removed, not shown as a full low bar."""
    sp = SpectrumProcessor(sample_rate=SR, bins=20)
    sig = _tone(1200, 1600) + 0.8   # big DC offset
    out = sp.process(sig)
    assert out[0] < 0.5, "DC offset must not pin the lowest band"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... -m pytest tests/test_indicator_dsp.py -q`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement SpectrumProcessor**

```python
# src/talktype/indicator_dsp.py
"""Frequency-band DSP for the recording indicator's 'bars' style.

Per-band background subtraction: each band learns its own quiet baseline and
shows only energy above it, so a steady tone (AC hum, mic DC offset) is
subtracted to nothing while speech transients pop. Pure numpy — no GTK — so it
is unit-tested without a display.
"""
import numpy as np


class SpectrumProcessor:
    def __init__(self, sample_rate=16000, ring_size=5600, bins=20,
                 freq_lo=110, freq_hi=4200):
        self.bins = bins
        self._ring = np.zeros(ring_size, dtype=np.float32)
        self._window = np.hanning(ring_size).astype(np.float32)
        freqs = np.fft.rfftfreq(ring_size, 1.0 / sample_rate)
        edges = np.linspace(freq_lo, freq_hi, bins + 1)
        self._slices = [np.where((freqs >= edges[i]) & (freqs < edges[i + 1]))[0]
                        for i in range(bins)]
        self._floor = np.zeros(bins, dtype=np.float32)
        self._ceil = np.full(bins, 1e-4, dtype=np.float32)

    def process(self, samples):
        samples = np.asarray(samples, dtype=np.float32)
        n = len(samples)
        if n >= len(self._ring):
            self._ring = samples[-len(self._ring):].copy()
        else:
            self._ring = np.concatenate([self._ring[n:], samples])

        win = (self._ring - self._ring.mean()) * self._window   # DC removal
        mag = np.abs(np.fft.rfft(win))
        raw = np.array([mag[idx].mean() if len(idx) else 0.0 for idx in self._slices])
        raw = np.log1p(raw * 4.0)

        below = raw < self._floor
        self._floor[below] = raw[below]
        self._floor[~below] += (raw[~below] - self._floor[~below]) * 0.02
        residual = np.maximum(0.0, raw - self._floor)

        up = residual > self._ceil
        self._ceil[up] = residual[up]
        self._ceil[~up] *= 0.99
        return np.clip(residual / (self._ceil + 1e-4), 0.0, 1.0).astype(np.float32)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `... -m pytest tests/test_indicator_dsp.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/talktype/indicator_dsp.py tests/test_indicator_dsp.py
git commit -m "Add per-band background-subtraction spectrum DSP for the bars style"
```

---

### Task 3: Color and backing helpers + the three style renderers

**Files:**
- Create: `src/talktype/indicator_styles.py`
- Test: `tests/test_indicator_styles.py`

**Interfaces:**
- Produces:
  - `BACKING_LEVELS: dict[str, float]` = `{"off":0.0,"soft":0.34,"medium":0.50,"strong":0.68}`
  - `resolve_color(mode: str, custom_hex: str, accent_rgb: tuple) -> tuple[float,float,float]`
  - `backing_alpha(r: float, core: float, plateau: float = 0.42) -> float`
  - `draw_backing(cr, cx, cy, rx, ry, core: float) -> None`
  - `draw_waveform(cr, w, h, samples, level, color_rgb, backing_core, sensitivity)`
  - `draw_bars(cr, w, h, spectrum, color_rgb, backing_core)`
  - `draw_radial(cr, w, h, samples, level, color_rgb, backing_core, sensitivity)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_indicator_styles.py
import math
import numpy as np
import pytest
from talktype import indicator_styles as S


def test_backing_alpha_endpoints_and_monotonic():
    assert S.backing_alpha(0.0, 0.5) == pytest.approx(0.5)
    assert S.backing_alpha(1.0, 0.5) == pytest.approx(0.0, abs=1e-9)
    # non-increasing across the taper
    xs = [i / 50 for i in range(51)]
    vals = [S.backing_alpha(r, 0.5) for r in xs]
    assert all(vals[i] >= vals[i + 1] - 1e-9 for i in range(len(vals) - 1))


def test_backing_levels_have_the_four_names():
    assert set(S.BACKING_LEVELS) == {"off", "soft", "medium", "strong"}
    assert S.BACKING_LEVELS["off"] == 0.0


def test_resolve_color_system_uses_accent():
    assert S.resolve_color("system", "#48b7f5", (0.2, 0.4, 0.26)) == (0.2, 0.4, 0.26)


def test_resolve_color_custom_parses_hex():
    r, g, b = S.resolve_color("custom", "#ff8000", (0, 0, 0))
    assert r == pytest.approx(1.0, abs=0.01)
    assert g == pytest.approx(0.5, abs=0.02)
    assert b == pytest.approx(0.0, abs=0.01)


def _surface_has_ink(draw):
    """Render onto a headless ARGB surface and assert something was drawn."""
    cairo = pytest.importorskip("cairo")
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 120)
    cr = cairo.Context(surf)
    draw(cr)
    surf.flush()
    buf = surf.get_data()
    return any(b != 0 for b in buf)


def test_waveform_draws_something():
    s = (0.3 * np.sin(np.linspace(0, 20, 800))).astype(np.float32)
    assert _surface_has_ink(lambda cr: S.draw_waveform(cr, 200, 120, s, 0.6, (0.3, 0.7, 0.96), 0.5, 1.0))


def test_bars_draw_something():
    spec = np.linspace(0.1, 1.0, 20).astype(np.float32)
    assert _surface_has_ink(lambda cr: S.draw_bars(cr, 200, 120, spec, (0.3, 0.7, 0.96), 0.5))


def test_radial_draws_something():
    s = (0.3 * np.sin(np.linspace(0, 20, 800))).astype(np.float32)
    assert _surface_has_ink(lambda cr: S.draw_radial(cr, 200, 120, s, 0.6, (0.3, 0.7, 0.96), 0.5, 1.0))


def test_draw_with_backing_off_still_draws_the_visualization():
    spec = np.linspace(0.1, 1.0, 20).astype(np.float32)
    assert _surface_has_ink(lambda cr: S.draw_bars(cr, 200, 120, spec, (0.3, 0.7, 0.96), 0.0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... -m pytest tests/test_indicator_styles.py -q`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the helpers and renderers**

```python
# src/talktype/indicator_styles.py
"""Cairo drawing for the recording indicator's new styles + the soft backing.

Pure cairo (no GTK widget), so every renderer is testable by drawing onto an
ImageSurface with no display. Geometry and colour choices here were settled by
live prototyping with Ron; see
docs/superpowers/specs/2026-08-14-recording-indicator-styles-design.md.
"""
import math

import cairo

BACKING_LEVELS = {"off": 0.0, "soft": 0.34, "medium": 0.50, "strong": 0.68}


def resolve_color(mode, custom_hex, accent_rgb):
    """(r,g,b) 0..1 for the active color mode."""
    if mode == "custom":
        h = custom_hex.lstrip("#")
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return tuple(accent_rgb)


def _fg(base, intensity, alpha=None):
    t = 0.35 * intensity
    rgb = tuple(base[i] + (1.0 - base[i]) * t for i in range(3))
    return (*rgb, alpha if alpha is not None else 0.82 + 0.18 * intensity)


def backing_alpha(r, core, plateau=0.42):
    if core <= 0.0:
        return 0.0
    if r <= plateau:
        return core
    t = (r - plateau) / (1.0 - plateau)
    return core * (0.5 + 0.5 * math.cos(math.pi * t))


def draw_backing(cr, cx, cy, rx, ry, core):
    """Feathered dark backing: flat core, raised-cosine taper to zero, sampled
    across many stops so no ring shows and it dissolves at the edge."""
    if core <= 0.001:
        return
    cr.save(); cr.translate(cx, cy); cr.scale(rx, ry)
    g = cairo.RadialGradient(0, 0, 0, 0, 0, 1)
    N = 96
    for k in range(N + 1):
        r = k / N
        g.add_color_stop_rgba(r, 0.05, 0.06, 0.09, backing_alpha(r, core))
    cr.set_source(g); cr.arc(0, 0, 1, 0, 2 * math.pi); cr.fill(); cr.restore()


def draw_waveform(cr, w, h, samples, level, color_rgb, backing_core, sensitivity):
    draw_backing(cr, w / 2, h / 2, w * 0.48, h * 0.44)
    iw = w * 0.60
    x0 = (w - iw) / 2
    mid = h / 2
    amp = (h * 0.46 / 2) * 0.9
    n = int(iw)
    step = max(1, len(samples) // n)
    pts = samples[::step][:n]
    cr.new_path()
    for i, v in enumerate(pts):
        y = mid - max(-1.0, min(1.0, v * 3.0 * sensitivity)) * amp
        cr.line_to(x0 + i, y) if i else cr.move_to(x0 + i, y)
    cr.set_source_rgba(*_fg(color_rgb, min(1.0, level + 0.3)))
    cr.set_line_width(2.6); cr.stroke()


def draw_bars(cr, w, h, spectrum, color_rgb, backing_core):
    draw_backing(cr, w / 2, h / 2, w * 0.49, h * 0.46)
    iw = w * 0.52
    x0 = (w - iw) / 2
    n = len(spectrum); gap = 4
    bw = (iw - gap * (n - 1)) / n
    ch = h * 0.40
    baseline = h / 2 + ch / 2
    for i, mag in enumerate(spectrum):
        x = x0 + i * (bw + gap); bh = max(2, mag * ch)
        cr.set_source_rgba(*_fg(color_rgb, mag, alpha=0.64 + 0.36 * mag))
        cr.rectangle(x, baseline - bh, bw, bh); cr.fill()


def draw_radial(cr, w, h, samples, level, color_rgb, backing_core, sensitivity):
    cx, cy = w / 2, h / 2
    max_r = min(w, h) * 0.22
    draw_backing(cr, cx, cy, max_r + 46, max_r + 46)
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
    cr.set_line_width(2.6); cr.stroke()
    cr.set_source_rgba(*_fg(color_rgb, level, 0.8))
    cr.arc(cx, cy, base * 0.7 + level * 5, 0, 2 * math.pi); cr.fill()
```

Note: the module must be importable with the system cairo on `PYTHONPATH` (already the case for the test command). The `backing_core` parameter is passed through for symmetry even though `draw_backing` is called with fixed geometry; keep it so callers pass the resolved level once.

- [ ] **Step 4: Run tests to verify pass**

Run: `... -m pytest tests/test_indicator_styles.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/talktype/indicator_styles.py tests/test_indicator_styles.py
git commit -m "Add color/backing helpers and waveform/bars/radial renderers"
```

---

### Task 4: Wire the styles into RecordingIndicator

**Files:**
- Modify: `src/talktype/recording_indicator.py` (`__init__` ~line 57; `on_draw` ~line 270; `apply_settings` ~line 227; `set_audio_level` ~line 252)
- Test: `tests/test_indicator_widget_styles.py`

**Interfaces:**
- Consumes: Task 3 renderers + `BACKING_LEVELS`, `resolve_color`; Task 1 config fields.
- Produces: `RecordingIndicator(..., style=, color_mode=, custom_color=, backing=, sensitivity=, follow_system_color=)`; methods `set_waveform(samples)`, `set_spectrum(bands)`; extended `apply_settings(position, size, offset_x, offset_y, style=None, color_mode=None, custom_color=None, backing=None, sensitivity=None, follow_system_color=None)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_indicator_widget_styles.py
import numpy as np
import pytest


@pytest.fixture
def indicator():
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    if not Gtk.init_check(None)[0]:
        pytest.skip("no display")
    from talktype.recording_indicator import RecordingIndicator
    ind = RecordingIndicator(style="bars", size="medium")
    yield ind
    ind.destroy()
    while Gtk.events_pending():
        Gtk.main_iteration()


def test_style_is_stored(indicator):
    assert indicator.style == "bars"


def test_setters_store_data(indicator):
    indicator.set_waveform(np.zeros(100, dtype=np.float32))
    indicator.set_spectrum(np.linspace(0, 1, 20).astype(np.float32))
    assert indicator.waveform is not None
    assert indicator.spectrum is not None


def test_apply_settings_changes_style_live(indicator):
    indicator.apply_settings("center", "medium", 0, 0, style="radial")
    assert indicator.style == "radial"


def test_apply_settings_changes_backing_and_sensitivity(indicator):
    indicator.apply_settings("center", "medium", 0, 0, backing="strong", sensitivity=1.5)
    assert indicator.backing == "strong"
    assert indicator.sensitivity == 1.5


def test_orb_style_keeps_original_behavior(indicator):
    indicator.apply_settings("center", "medium", 0, 0, style="orb")
    assert indicator.style == "orb"
    # orb path still present
    assert hasattr(indicator, "draw_orb")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... -m pytest tests/test_indicator_widget_styles.py -q`
Expected: FAIL (unexpected kwargs / missing attributes).

- [ ] **Step 3: Extend `__init__`**

```python
# recording_indicator.py __init__ signature and body additions
    def __init__(self, position="center", offset_x=0, offset_y=0, size="medium",
                 style="orb", color_mode="system", custom_color="#48b7f5",
                 backing="medium", sensitivity=1.0, follow_system_color=False):
        ...
        self.style = style
        self.color_mode = color_mode
        self.custom_color = custom_color
        self.backing = backing
        self.sensitivity = sensitivity
        self.follow_system_color = follow_system_color
        self.waveform = None
        self.spectrum = None
```

- [ ] **Step 4: Add data setters**

```python
# recording_indicator.py, next to set_audio_level
    def set_waveform(self, samples):
        self.waveform = samples

    def set_spectrum(self, bands):
        self.spectrum = bands

    def _accent_rgb(self):
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk
            ok, rgba = Gtk.Label().get_style_context().lookup_color("theme_selected_bg_color")
            if ok:
                return (rgba.red, rgba.green, rgba.blue)
        except Exception:
            pass
        return (0.30, 0.72, 0.42)

    def _resolved_color(self):
        from .indicator_styles import resolve_color
        return resolve_color(self.color_mode, self.custom_color, self._accent_rgb())
```

- [ ] **Step 5: Dispatch in on_draw**

```python
# recording_indicator.py on_draw, after the transparent clear and before the orb block:
        if self.style != "orb":
            from . import indicator_styles as st
            core = st.BACKING_LEVELS.get(self.backing, 0.5)
            color = self._resolved_color()
            if self.style == "waveform":
                st.draw_waveform(cr, width, height, self.waveform if self.waveform is not None else [],
                                 self.audio_level, color, core, self.sensitivity)
            elif self.style == "bars":
                st.draw_bars(cr, width, height,
                             self.spectrum if self.spectrum is not None else [],
                             color, core)
            elif self.style == "radial":
                st.draw_radial(cr, width, height, self.waveform if self.waveform is not None else [],
                               self.audio_level, color, core, self.sensitivity)
            return
        # ---- orb path below is unchanged ----
```

When `follow_system_color` is set and style is orb, the orb path may recolor via
the accent; that is an orb-only concern handled in its own draw and out of scope
for the dispatch (orb draw path stays as today unless `follow_system_color`).

- [ ] **Step 6: Extend apply_settings**

```python
# recording_indicator.py apply_settings — add optional kwargs, applied when not None
    def apply_settings(self, position, size, offset_x, offset_y,
                       style=None, color_mode=None, custom_color=None,
                       backing=None, sensitivity=None, follow_system_color=None):
        # ... existing position/size/offset handling ...
        if style is not None:
            self.style = style
        if color_mode is not None:
            self.color_mode = color_mode
        if custom_color is not None:
            self.custom_color = custom_color
        if backing is not None:
            self.backing = backing
        if sensitivity is not None:
            self.sensitivity = sensitivity
        if follow_system_color is not None:
            self.follow_system_color = follow_system_color
```

- [ ] **Step 7: Run tests to verify pass**

Run: `... -m pytest tests/test_indicator_widget_styles.py tests/test_indicator_apply_settings.py -q`
Expected: PASS (existing apply_settings tests still pass).

- [ ] **Step 8: Commit**

```bash
git add src/talktype/recording_indicator.py tests/test_indicator_widget_styles.py
git commit -m "Dispatch recording indicator to the selected style, keep orb path intact"
```

---

### Task 5: Feed the active style's data from the audio callback

**Files:**
- Modify: `src/talktype/app.py` (audio callback ~line 560-570 where `set_audio_level` is called; construction of `RecordingIndicator` ~line 2407; `_reload_live_settings` ~line 742)
- Test: `tests/test_indicator_feed.py`

**Interfaces:**
- Consumes: `SpectrumProcessor` (Task 2); `RecordingIndicator.set_waveform/set_spectrum` (Task 4).
- Produces: `app._feed_indicator(indicator, int16_samples, spectrum_processor)` — computes only what the indicator's current style needs and calls the setters.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_indicator_feed.py
import numpy as np
import pytest


@pytest.fixture
def app():
    return pytest.importorskip("talktype.app")


class StubInd:
    def __init__(self, style):
        self.style = style
        self.level = None
        self.waveform = None
        self.spectrum = None
    def set_audio_level(self, v): self.level = v
    def set_waveform(self, s): self.waveform = s
    def set_spectrum(self, b): self.spectrum = b


def _samples():
    return (np.sin(np.linspace(0, 40, 512)) * 8000).astype(np.int16)


def test_orb_gets_level_only(app):
    ind = StubInd("orb")
    app._feed_indicator(ind, _samples(), None)
    assert ind.level is not None
    assert ind.waveform is None and ind.spectrum is None


def test_waveform_style_gets_samples(app):
    ind = StubInd("waveform")
    app._feed_indicator(ind, _samples(), None)
    assert ind.waveform is not None


def test_bars_style_gets_spectrum(app):
    from talktype.indicator_dsp import SpectrumProcessor
    ind = StubInd("bars")
    app._feed_indicator(ind, _samples(), SpectrumProcessor(bins=20))
    assert ind.spectrum is not None and len(ind.spectrum) == 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... -m pytest tests/test_indicator_feed.py -q`
Expected: FAIL (`_feed_indicator` not defined).

- [ ] **Step 3: Implement `_feed_indicator` and use it**

```python
# app.py, module level
def _feed_indicator(indicator, int16_samples, spectrum_processor):
    """Feed only the data the active style needs. Level is always cheap and
    drives the orb and the color brightness; samples/FFT are computed only when
    the chosen style consumes them."""
    import numpy as np
    audio = np.frombuffer(int16_samples, dtype=np.int16).astype(np.float32)
    rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) else 0.0
    indicator.set_audio_level(min(1.0, rms / 3000.0))

    style = getattr(indicator, "style", "orb")
    if style in ("waveform", "radial"):
        indicator.set_waveform(audio / 32768.0)
    elif style == "bars" and spectrum_processor is not None:
        indicator.set_spectrum(spectrum_processor.process(audio / 32768.0))
```

```python
# app.py, where the indicator is constructed (~line 2407), build a processor:
            from .indicator_dsp import SpectrumProcessor
            _spectrum_processor = SpectrumProcessor(bins=20)
```

```python
# app.py, in the audio callback, REPLACE the direct set_audio_level call:
            _feed_indicator(recording_indicator, indata, _spectrum_processor)
```

(Where `indata` is the int16 buffer already read in that callback; keep the
existing `recording_indicator is not None` guard around the call.)

- [ ] **Step 4: Pass the new fields when constructing the indicator**

```python
# app.py, RecordingIndicator(...) construction — add the new kwargs from cfg
                    recording_indicator = RecordingIndicator(
                        position=cfg.indicator_position,
                        offset_x=cfg.indicator_offset_x,
                        offset_y=cfg.indicator_offset_y,
                        size=cfg.indicator_size,
                        style=cfg.indicator_style,
                        color_mode=cfg.indicator_color_mode,
                        custom_color=cfg.indicator_color,
                        backing=cfg.indicator_backing,
                        sensitivity=cfg.indicator_sensitivity,
                        follow_system_color=cfg.orb_follow_system_color,
                    )
```

- [ ] **Step 5: Pass the new fields through the live reload**

```python
# app.py _reload_live_settings, in the indicator.apply_settings(...) call
        indicator.apply_settings(
            cfg.indicator_position, cfg.indicator_size,
            cfg.indicator_offset_x, cfg.indicator_offset_y,
            style=cfg.indicator_style,
            color_mode=cfg.indicator_color_mode,
            custom_color=cfg.indicator_color,
            backing=cfg.indicator_backing,
            sensitivity=cfg.indicator_sensitivity,
            follow_system_color=cfg.orb_follow_system_color,
        )
```

- [ ] **Step 6: Run tests to verify pass**

Run: `... -m pytest tests/test_indicator_feed.py tests/test_live_settings_reload.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/talktype/app.py tests/test_indicator_feed.py
git commit -m "Feed the active indicator style its data from the audio callback"
```

---

### Task 6: Preferences controls (Style, Color, Backing, Sensitivity)

**Files:**
- Modify: `src/talktype/prefs.py` (recording-indicator section that builds `indicator_position`/`indicator_size` combos, ~line 1074-1178)
- Test: `tests/test_prefs_indicator_controls.py`

**Interfaces:**
- Consumes: config fields (Task 1); writes through the existing `self.update_config(key, value)`.
- Produces: source contains a Style combo, a Color control with a system-accent option, a Backing combo, and a Sensitivity slider, all writing the Task 1 keys; all labels use "Color".

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prefs_indicator_controls.py
import pathlib
PREFS = pathlib.Path(__file__).resolve().parent.parent / "src/talktype/prefs.py"


def test_controls_write_the_new_config_keys():
    text = PREFS.read_text()
    for key in ("indicator_style", "indicator_color_mode", "indicator_color",
                "indicator_backing", "indicator_sensitivity"):
        assert key in text, f"Preferences never writes {key}"


def test_uses_american_spelling_for_color_labels():
    text = PREFS.read_text()
    # No British 'Colour' in any user-facing string.
    assert "Colour" not in text


def test_style_options_present():
    text = PREFS.read_text()
    for style in ("orb", "waveform", "bars", "radial"):
        assert style in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... -m pytest tests/test_prefs_indicator_controls.py -q`
Expected: FAIL (keys/labels absent).

- [ ] **Step 3: Add the Style combo**

```python
# prefs.py, in the recording-indicator section near the indicator_size combo
        style_combo = Gtk.ComboBoxText()
        for sid, slabel in (("orb", "Orb (classic)"), ("waveform", "Waveform"),
                            ("bars", "Frequency bars"), ("radial", "Radial")):
            style_combo.append(sid, slabel)
        style_combo.set_active_id(self.config.get("indicator_style", "orb"))
        style_combo.connect("changed", lambda x: self.update_config("indicator_style", x.get_active_id()))
        grid.attach(style_combo, 1, row, 1, 1); row += 1
```

- [ ] **Step 4: Add the Backing combo**

```python
# prefs.py, same section
        backing_combo = Gtk.ComboBoxText()
        for bid, blabel in (("off", "Off (transparent)"), ("soft", "Soft"),
                           ("medium", "Medium"), ("strong", "Strong")):
            backing_combo.append(bid, blabel)
        backing_combo.set_active_id(self.config.get("indicator_backing", "medium"))
        backing_combo.connect("changed", lambda x: self.update_config("indicator_backing", x.get_active_id()))
        grid.attach(backing_combo, 1, row, 1, 1); row += 1
```

- [ ] **Step 5: Add the Sensitivity slider**

```python
# prefs.py, same section
        sens = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.5, 2.0, 0.1)
        sens.set_value(self.config.get("indicator_sensitivity", 1.0))
        sens.connect("value-changed", lambda x: self.update_config("indicator_sensitivity", round(x.get_value(), 2)))
        grid.attach(sens, 1, row, 1, 1); row += 1
```

- [ ] **Step 6: Add the Color control (picker + system accent)**

```python
# prefs.py, same section — a mode combo plus a color button (American 'Color')
        color_mode = Gtk.ComboBoxText()
        color_mode.append("system", "Use system accent color")
        color_mode.append("custom", "Custom color")
        color_mode.set_active_id(self.config.get("indicator_color_mode", "system"))
        color_mode.connect("changed", lambda x: self.update_config("indicator_color_mode", x.get_active_id()))
        grid.attach(color_mode, 1, row, 1, 1); row += 1

        from gi.repository import Gdk
        color_btn = Gtk.ColorButton()
        rgba = Gdk.RGBA(); rgba.parse(self.config.get("indicator_color", "#48b7f5"))
        color_btn.set_rgba(rgba)

        def _on_color(btn):
            c = btn.get_rgba()
            self.update_config("indicator_color",
                               "#%02x%02x%02x" % (int(c.red * 255), int(c.green * 255), int(c.blue * 255)))
            self.update_config("indicator_color_mode", "custom")
        color_btn.connect("color-set", _on_color)
        grid.attach(color_btn, 1, row, 1, 1); row += 1

        # Orb-only: follow the system accent instead of the classic cyan.
        orb_follow = Gtk.CheckButton(label="Orb follows system accent color")
        orb_follow.set_active(self.config.get("orb_follow_system_color", False))
        orb_follow.connect("toggled", lambda x: self.update_config("orb_follow_system_color", x.get_active()))
        grid.attach(orb_follow, 0, row, 2, 1); row += 1
```

- [ ] **Step 7: Run tests to verify pass, then the full suite**

Run: `... -m pytest tests/test_prefs_indicator_controls.py -q`
Then: `... -m pytest tests/ -q`
Expected: PASS; full suite green.

- [ ] **Step 8: Manual verification (Ron)**

Launch the dev app, open Preferences, switch style/color/backing/sensitivity, and confirm each takes effect on the next dictation with no restart. Confirm the orb is unchanged and, with the checkbox, optionally follows the accent.

- [ ] **Step 9: Commit**

```bash
git add src/talktype/prefs.py tests/test_prefs_indicator_controls.py
git commit -m "Add Style, Color, Backing and Sensitivity controls to Preferences"
```

---

## Self-Review

**Spec coverage:**
- Four styles → Tasks 3 (renderers), 4 (dispatch, orb kept). ✓
- Color picker + system accent, American spelling → Tasks 3 (resolve_color), 6 (UI). ✓
- Backing off/soft/medium/strong, cosine feather → Task 3 (`backing_alpha`, `draw_backing`, `BACKING_LEVELS`). ✓
- Sizes small/medium/large → existing `indicator_size`, carried through construction/apply_settings (Tasks 4-5). ✓
- Sensitivity → Tasks 1, 3 (used in renderers), 6. ✓
- Bars background subtraction → Task 2. ✓
- Data path, active-style-only compute → Task 5. ✓
- Live-apply, no restart → Task 1 (LIVE_APPLIED_KEYS) + Task 5 (`_reload_live_settings`). ✓
- Orb unchanged → Task 4 keeps the orb draw path; Task 4 test asserts it. ✓
- Defaults (orb/system/medium/1.0) → Task 1. ✓

**Placeholder scan:** No TBD/TODO; every code step has real code. The one prose note (orb `follow_system_color` recolor) is scoped as orb-only and does not block the dispatch; if desired it is a small follow-up on the orb draw path, but the checkbox + config + live-apply are all delivered.

**Type consistency:** `set_waveform`/`set_spectrum`, `resolve_color(mode, custom_hex, accent_rgb)`, `BACKING_LEVELS`, `_feed_indicator(indicator, int16_samples, spectrum_processor)`, and the `apply_settings` kwargs are named identically across Tasks 3-6. ✓

**Known small gap:** the orb's *own* recoloring when `orb_follow_system_color` is true is represented as config + UI + live-apply but its draw-path recolor is intentionally left as a minimal orb-only follow-up (a subclass-style hue swap proven in prototyping), to keep the orb path otherwise untouched in this plan.

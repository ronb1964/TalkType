# Recording indicator: selectable styles, color, and backing

**Date:** 2026-08-14
**Status:** Design settled with Ron via live prototypes; not yet implemented

## Summary

Today the recording indicator is a single fixed design: a cyan orb with a dark
pill, a red recording border, a timer, and particles that extend with your
voice. This adds **three new visualisation styles** alongside it, each
**color-selectable** and drawn over a **soft dark backing** so it stays legible
on any desktop, plus a **sensitivity** control. All of it applies live through
the config-watch mechanism already built (no service restart).

The visuals were chosen by iterating real transparent overlays over Ron's actual
desktop, driven by his live microphone — not from mockups.

## Styles (four total)

| Style | What it is | Data it needs |
|---|---|---|
| **Orb** (existing) | Today's cyan orb, unchanged | RMS level (as now) |
| **Waveform** | Oscilloscope line, voice scrolling across | raw sample buffer |
| **Frequency bars** | Spectrum bars, background-subtracted | FFT magnitudes |
| **Radial** | A closed waveform wrapped into a ring | raw sample buffer |

The orb is kept exactly as it is and stays the default. The three new styles are
bare, floating visualisations (no pill, no red border, no timer — those belong
to the orb alone; Ron was explicit about that).

## Color (American spelling throughout the UI)

- **Orb:** original cyan by default, with an option to **follow the system
  accent** instead. When following, only the orb's hue changes; the pill, red
  border, timer, particle geometry and flare are identical (proven by a subclass
  that copied the geometry verbatim and swapped only colors).
- **New styles:** a **color picker** (any color) plus a **System accent**
  shortcut. Because the backing guarantees legibility, color is a free aesthetic
  choice, not a contrast constraint.
- The color brightens slightly toward white with louder input, so there is
  loudness feedback in any color.

**Proposed default for the new styles:** follow the system accent, so they look
integrated out of the box. (Confirm in review.)

## Backing (the soft "smoky" background)

The new styles are transparent floating windows, so with nothing behind them
their legibility depends on the desktop. A **soft dark backing** — the orb's
pill idea, but borderless and feathered — solves that universally: bright colors
pop against dark, and over a dark desktop the scrim is nearly invisible while
over a light one it provides contrast.

- Levels: **Off (fully transparent) · Soft · Medium · Strong**. Off gives the
  clean minimal look; the others guarantee legibility. Ron approved the three
  on-levels' strengths.
- The backing is a radial gradient with a flat core then a **raised-cosine taper
  to zero**, sampled across ~96 stops. The cosine lands at the edge with zero
  slope (dissolves, no outline); the many stops remove the faint rings that few
  stops produced (cairo draws straight lines between stops).
- The backing is **sized per style** and must feather entirely **inside** the
  window, or the window clips it into a hard edge. It must also fully
  **encompass** the content with margin — the content is drawn smaller and
  centered, the fade happens in the empty margin around it. Bars use a wider
  ellipse (wide, short content); the radial uses a tight one that hugs it.

**Proposed default backing:** Medium. (Confirm in review.)

## Sizes

Small / medium / large, reusing the existing `indicator_size` scaling. Applies
to all four styles.

## Sensitivity

A slider scaling how strongly input drives the animation. The app maps loudness
as `rms / 3000` on int16 samples; sensitivity multiplies that. Default 1.0,
range roughly 0.5–2.0. Matching this scaling is also what makes a preview flare
like production — it is the same number.

## Frequency-bar signal processing

Raw speech and room noise are dominated by low frequencies, so naive per-frame
normalisation pins the low bars and everything ramps down from the left. The
bars instead use **per-band background subtraction**:

- Remove the DC component (subtract the mean) before the FFT.
- Ignore everything below ~110 Hz (mic offset, AC hum, room rumble — below
  speech).
- For each display band, track a slowly-rising **floor** (drops instantly to a
  new quiet level, creeps up toward steady energy) and a fast-attack/slow-decay
  **ceiling**; display `(value − floor) / ceiling`.

A steady tone (an air conditioner) is learned as baseline and subtracted to
nothing, so a quiet room reads flat and speech transients pop across the whole
width. Ron confirmed: bars sit at zero when silent, react fully when talking.

## Architecture

### Data path (service → indicator, same process)

`app.py`'s audio callback already computes RMS from int16 samples and calls
`recording_indicator.set_audio_level()`. It gains, **only for the active
style**:

- a rolling **sample buffer** (waveform, radial),
- a **background-subtracted spectrum** (bars).

Computed only when needed — no FFT when the style is orb or waveform. Fed to the
indicator by direct method calls (same process; no IPC). The audio callback runs
on a capture thread and the indicator draws on the GTK main thread; sample/
spectrum hand-off follows the existing `set_audio_level` cross-thread pattern
(numpy array / float assignment; a lock or tolerated tearing — harmless for a
visualiser).

### RecordingIndicator

Gains:

- `style` — dispatches `on_draw` to the per-style renderer; orb keeps its exact
  current code path.
- `color` + whether it follows the system accent; the accent is read via
  `lookup_color("theme_selected_bg_color")` (same source as the Preferences
  stylesheet).
- `backing_level` and the shared feathered-backing helper (the three new styles
  draw it; the orb keeps its pill).
- `sensitivity`.
- data setters for samples / spectrum.

`apply_settings()` (added in the live-settings work) extends to carry style,
color, backing and sensitivity so they apply to a running indicator.

### Config (new keys, American spelling)

- `indicator_style`: `orb` | `waveform` | `bars` | `radial` (default `orb`)
- `indicator_color_mode`: `system` | `custom` (new styles); orb uses
  `original` | `system`
- `indicator_color`: the custom color (hex)
- `indicator_backing`: `off` | `soft` | `medium` | `strong` (default `medium`)
- `indicator_sensitivity`: float (default 1.0)

All added to `config.LIVE_APPLIED_KEYS`, so every one applies without a service
restart — the mechanism built on 2026-08-13. The coverage test then forces each
new key to be classified.

### Preferences UI

Under the existing recording-indicator section: a **Style** dropdown, a
**Color** control (picker + "Use system accent"), a **Backing** dropdown, and a
**Sensitivity** slider — all labelled with American "Color". The controls that
only apply to some styles (color, backing) can stay enabled for all; they simply
have no effect on the orb, which owns its own look.

### GNOME extension

The extension mirrors the tray menu but does not draw the indicator, so it needs
no change. If a quick style switch is ever wanted in the panel menu, that is a
separate follow-up.

## Out of scope

- A glow/halo around the new styles — the backing provides presence; a separate
  glow was tried and judged unnecessary.
- Wrapping the new styles in the orb's pill/border/timer container — tried and
  rejected; the new styles float bare.
- Per-style animation tuning beyond what is described.

## Testing

- Background subtraction: a steady synthetic tone decays to ~zero in its band;
  an impulse shows and then settles.
- Backing geometry: the feather reaches zero strictly inside the window for
  every style and size (no clip); the content bounding box sits inside the
  backing's core.
- Sensitivity scales the drawn amplitude/extent monotonically.
- Color-mode resolution: system mode tracks the theme accent; custom mode uses
  the stored color; orb original mode is unchanged.
- Every new config key is in `LIVE_APPLIED_KEYS` (the coverage test already
  enforces total classification) and applies via the config watch without a
  restart.
- The orb style renders byte-for-byte as today (its code path is untouched).

## Success criteria

A user opens Preferences, picks a style, a color (or system accent), a backing
level, a size and a sensitivity, and the recording indicator changes on the next
dictation with no restart. The orb is unchanged for anyone who keeps it. The new
styles are legible on any desktop and react cleanly to the voice, with a quiet
room reading calm.

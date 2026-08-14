# Apply recording-indicator settings without restarting the service

**Date:** 2026-08-13
**Status:** Approved, not yet implemented

## Problem

Changing any setting in Preferences and pressing Apply or OK restarts the
dictation service. The restart takes roughly ten seconds, measured on this
machine:

| Step | Elapsed |
|---|---|
| Preferences kills the service, waits | 1.0s (deliberate `sleep`) |
| Python imports torch / CTranslate2 | ~3s |
| D-Bus service up, indicator constructed | — |
| Gap before model load begins | ~4.0s |
| large-v3 loaded onto CUDA | ~1.35s |

During that window F8 does nothing at all: no start beep, no indicator, no
message. Nothing tells the user the service is down or coming back.

The restart is almost always unnecessary. Moving the recording indicator twenty
pixels currently tears down the service and reloads a 3 GB Whisper model onto
the GPU. Only `model` and `device` genuinely need that.

## Why this is not simply "skip the restart"

`app.py::main()` calls `load_config()` **once**, at startup. Every downstream
consumer — hotkeys, indicator, beeps, punctuation, injection mode — reads that
single object. There is no live-reload path of any kind.

So the work is not skipping a restart; it is adding a way to apply settings to
a running service, and then skipping the restart for the settings that path
covers.

## Scope

**In scope:** `indicator_position`, `indicator_size`, `indicator_offset_x`,
`indicator_offset_y`.

**Explicitly out of scope**, and why:

- `recording_indicator` (the on/off toggle) — applying it live means
  constructing a GTK window from the polling path mid-flight. Low value, real
  risk. Stays restart-required.
- Hotkeys — changing these live means re-grabbing input devices on a running
  service, the same machinery behind the system-wide keyboard lockups fixed in
  v0.6.0. Deserves its own design if wanted.
- Text behaviour, beeps, language — plausibly safe, but not asked for. YAGNI.

## Enabling detail

`show_at_position()` reads `self.position`, `self.scale`, `self.offset_x` and
`self.offset_y` **at show time**, not at construction. Applying new settings to
a running service is therefore just updating attributes on the existing object;
the next press of F8 shows the indicator in the new place. No window
recreation, no restart.

## Design

### Data flow

1. Preferences saves the config, unchanged from today.
2. Preferences computes which keys this save actually changed and, if they are
   a subset of `LIVE_APPLIED_KEYS`, skips the restart. Otherwise it restarts
   exactly as now.
3. The service's main loop checks the config file's mtime on a ~1s throttle —
   the same shape as the existing 3-second device rescan already in that loop.
   On change it reloads the config and pushes the values onto the live
   indicator.

### Components

**`RecordingIndicator.apply_settings(position, size, offset_x, offset_y)`**
Updates the attributes; when the size changed, updates `self.scale` and
resizes the window. Returns nothing. Safe to call while the indicator is
visible — position changes take effect at the next show, so the orb never jumps
mid-dictation.

**`app.py` main loop**
A throttled block mirroring `_rediscover_devices`:

```
if current_time - last_config_check >= CONFIG_RECHECK_SECONDS:
    last_config_check = current_time
    _reload_indicator_settings_if_changed(recording_indicator)
```

**`config.changed_keys(original, current) -> set[str]`**
A new helper exposing the comparison `merge_changed_keys` already performs
internally:

```python
def changed_keys(original, current):
    return {k for k, v in current.items() if k not in original or original[k] != v}
```

`merge_changed_keys` must be rewritten to call it, so the two definitions of
"changed" cannot drift apart. Duplicated logic hardened in only one copy is the
single most common defect in this codebase's history — including the bug that
prompted this spec, where the service was launched from two places and only one
set `GDK_BACKEND`.

**`prefs.py`**
`LIVE_APPLIED_KEYS = {"indicator_position", "indicator_size",
"indicator_offset_x", "indicator_offset_y"}`.

The restart decision uses the same two dicts `save_config()` already holds —
`self._config_at_open` (config when the window opened) and `self.config` (UI
state at save time):

```python
changed = changed_keys(self._config_at_open, self.config)
needs_restart = bool(changed - LIVE_APPLIED_KEYS)
```

An empty change set means nothing was modified, so no restart either way. Note
this deliberately measures what *the user changed in this window*, not what
differs on disk — a model switch made by the tray while Preferences was open is
already live in the service and must not trigger a restart.

### Why config-watching rather than a D-Bus method

A `ApplyIndicatorSettings` D-Bus method would be instant rather than
sub-second, and explicit. It was rejected because:

- It adds IPC surface that must be wired correctly on both sides.
  `DBusService._dispatch` only forwards to methods the app object actually has,
  and `SetModel` silently did nothing for several releases because
  `TrayAppInstance` had no `set_model`. Nothing caught it.
- It only covers changes made through Preferences. Config-watching also covers
  the tray and a hand-edited TOML.
- Sub-second latency is irrelevant for moving an orb.

Cost of the chosen approach is one `stat()` per second.

### Error handling

If the config is unreadable or damaged when the poll fires, `load_config()`
raises `ConfigNotLoadedError`. Keep the current settings, log **once** rather
than every second, and carry on. A damaged config must never degrade a running
dictation session — the same principle applied to the config-durability work in
v0.6.0.

### Included fix: window size ignores the scale

`__init__` calls `set_default_size(200, 180)` unscaled, while
`show_at_position()` computes `int(200 * self.scale)` for its positioning
maths. At `size = "large"` (1.4×) the maths assumes a 280×252 window that is
actually 200×180, so right- and bottom-anchored positions land roughly 80px
away from where they should. This is pre-existing, not a regression, but it is
in the code being changed and would otherwise make the live-resize path
inconsistent with the position path.

## Testing

- `apply_settings` updates position and offsets; changing size updates
  `self.scale` and the window size together.
- `changed_keys` returns exactly the keys that differ, including keys absent
  from `original`, and `merge_changed_keys` overlays exactly that set — proving
  the two stay in agreement.
- Restart decision: indicator-only change → no restart; `model` change →
  restart; mixed change → restart; no change → no restart.
- The mtime helper reports a change once and not again for an unchanged file.
- A damaged config during a poll leaves the previous settings intact and does
  not raise into the loop.
- Regression: window size matches the scale used by the positioning maths.

## Success criteria

Changing the indicator position in Preferences and pressing OK moves the
indicator on the next dictation, with no service restart, no model reload and
no gap where F8 is dead. Changing the model still restarts, as it must.

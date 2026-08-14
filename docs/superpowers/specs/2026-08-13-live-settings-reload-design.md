# Apply settings without restarting the dictation service

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

Almost none of that work is needed. Toggling auto-punctuation currently tears
down the service and reloads a 3 GB Whisper model onto the GPU. Only `model`
and `device` genuinely require it, because the model is what gets rebuilt.

## What makes this cheap

`app.py::main()` calls `load_config()` **once** and holds the resulting
`Settings` object for the life of the process. Most settings are then read off
that object **at the moment they are used** — every dictation ends with:

```python
stop_recording(cfg.beeps, cfg.smart_quotes, cfg.notify, cfg.language,
               cfg.auto_space, cfg.auto_period, cfg.injection_mode)
```

So refreshing the fields of that existing object makes those settings live with
no further work. Only values *copied into local variables at startup* need
explicit re-application.

## Scope

Settings fall into three groups, established by reading every consumer:

**Group 0 — the service never reads them.** Zero references in `app.py`:
`launch_at_login`, `auto_check_updates`, `last_update_check`, `language_mode`.
These are Preferences and tray concerns — `launch_at_login` writes an autostart
file, the update keys drive the tray's checker, and `language_mode` only decides
what Preferences writes into `language`, which is the field the service actually
reads. They need no restart and no reload; they must nonetheless appear in
`LIVE_APPLIED_KEYS`, or toggling "Launch at login" still costs a ten-second
model reload for nothing.

**Group 1 — live for free.** Read off `cfg` at point of use:
`beeps`, `notify`, `smart_quotes`, `language`, `auto_space`, `auto_period`,
`injection_mode`, `auto_timeout_enabled`, `auto_timeout_minutes`.

**Group 2 — live with small, contained work.** Copied into locals or objects at
startup, so they need explicit re-application:

| Setting | What must be redone |
|---|---|
| `hotkey`, `toggle_hotkey` | Recompute `hold_key` / `toggle_key` keycodes |
| `voice_commands_hotkey` | Re-parse the combo string |
| `mode` | Re-read the hold/toggle string |
| `typing_delay` | Reassign the `_typing_delay` module global |
| `indicator_position`, `indicator_size`, `indicator_offset_x`, `indicator_offset_y` | `apply_settings()` on the existing indicator |

**Group 3 — genuinely require a restart:** `model`, `device`. The `WhisperModel`
is constructed once; rebuilding it is the ten seconds.

**Already dynamic:** `mic` is re-resolved on stream failure and needs nothing.

**Out of scope:** `recording_indicator` (the on/off toggle) stays
restart-required — turning it on live means constructing a GTK window from the
polling path mid-flight, which is real risk for a setting nobody toggles often.

**Noted, not addressed:** `paste_injection` exists in `Settings` but appears
nowhere outside `config.py` — it reads as a dead setting. Left out of the
allowlist so it conservatively triggers a restart; whether to delete it is a
separate question, not this change's business.

Every field of `Settings` is accounted for by one of the groups above. A test
enforces that, so a newly added setting cannot be silently forgotten.

### A correction worth recording

An earlier draft treated hotkeys as high-risk on the grounds that changing them
live means re-grabbing input devices, the machinery behind the system-wide
keyboard lockups fixed in v0.6.0. **That was wrong.** Device grabbing happens
when *recording starts* (`_grab_all_devices`) and is independent of which
keycode is the hotkey; the event loop merely compares `event.code` against two
integers. Changing a hotkey live recomputes those integers and touches no grab
logic.

## Design

### Data flow

1. Preferences saves the config, unchanged from today.
2. Preferences computes which keys this save changed. If they are a subset of
   `LIVE_APPLIED_KEYS`, it **skips the restart**. Otherwise it restarts as now.
3. The service's main loop checks the config file's mtime on a ~1s throttle —
   the same shape as the existing 3-second device rescan already in that loop.
   On change it re-reads the file, refreshes the live `cfg` object in place, and
   re-applies the Group 2 values.

### Components

**`config.changed_keys(original, current) -> set[str]`**
Exposes the comparison `merge_changed_keys` already performs internally:

```python
def changed_keys(original, current):
    return {k for k, v in current.items() if k not in original or original[k] != v}
```

`merge_changed_keys` must be rewritten to call it, so the two definitions of
"changed" cannot drift apart. Duplicated logic hardened in only one copy is the
most common defect in this codebase's history — including the bug that prompted
this work, where the service was launched from two places and only one set
`GDK_BACKEND`.

**`app.py` — a throttled reload in the main loop**

```
if current_time - last_config_check >= CONFIG_RECHECK_SECONDS:
    last_config_check = current_time
    _reload_live_settings(cfg, recording_indicator, state)
```

`_reload_live_settings` re-reads the config, copies the Group 1 fields onto the
existing `cfg` object, and re-applies Group 2. It returns the recomputed
keycodes so the event loop can pick them up, rather than mutating loop locals
behind its back.

**`RecordingIndicator.apply_settings(position, size, offset_x, offset_y)`**
Updates the attributes and, when the size changed, `self.scale` and the window
size. `show_at_position()` already reads all four at show time, so a position
change takes effect at the next dictation and never moves the orb mid-recording.

**`prefs.py`**
An explicit `LIVE_APPLIED_KEYS` allowlist naming every Group 1 and Group 2 key.
The restart decision uses the two dicts `save_config()` already holds:

```python
changed = changed_keys(self._config_at_open, self.config)
needs_restart = bool(changed - LIVE_APPLIED_KEYS)
```

An empty change set means nothing was modified, so no restart either way.

This deliberately measures what *the user changed in this window*, not what
differs on disk — a model switch made by the tray while Preferences was open is
already live in the service and must not trigger a restart.

### Allowlist, not denylist — deliberately

`LIVE_APPLIED_KEYS` names what is *known* live. Expressing it the other way
round (`RESTART_REQUIRED = {model, device}`) would be shorter but fails in the
wrong direction: a setting added later would default to "live", silently not
apply, and present as a setting that lies about itself — the exact class of bug
v0.6.0 spent four commits eliminating. With an allowlist, a forgotten new
setting merely costs a restart.

### Error handling

If the config is unreadable or damaged when the poll fires, `load_config()`
raises `ConfigNotLoadedError`. Keep the current settings, log **once** rather
than every second, and carry on. A damaged config must never degrade a running
dictation session.

Settings are refreshed from the loop thread while the transcription path may be
reading them. Python attribute reads and writes are atomic, so no torn state is
possible; the worst case is one dictation using a mix of old and new values,
which is harmless for every key in scope.

### Included fix: window size ignores the scale

`__init__` calls `set_default_size(200, 180)` unscaled, while
`show_at_position()` computes `int(200 * self.scale)` for its positioning
maths. At `size = "large"` (1.4×) the maths assumes a 280×252 window that is
actually 200×180, so right- and bottom-anchored positions land roughly 80px
away from where they should. Pre-existing rather than a regression, but it is in
the code being changed and would otherwise make the live-resize path
inconsistent with the position path.

## Testing

- `changed_keys` returns exactly the differing keys, including keys absent from
  `original`; `merge_changed_keys` overlays exactly that set.
- Restart decision: Group 1 or 2 change → no restart; `model` change → restart;
  mixed change → restart; no change → no restart; an **unknown** key → restart.
- `_reload_live_settings` refreshes Group 1 fields on the existing object and
  returns recomputed keycodes when the hotkey changed.
- `apply_settings` updates position and offsets; changing size updates
  `self.scale` and the window size together.
- A damaged config during a poll leaves previous settings intact and does not
  raise into the loop.
- Regression: window size matches the scale used by the positioning maths.
- **Coverage:** every field of `Settings` is either in `LIVE_APPLIED_KEYS` or in
  a documented restart-required set. A new setting added later fails this test
  rather than silently defaulting to either behaviour.

## Success criteria

Changing punctuation, beeps, language, injection mode, hotkeys, hold/toggle
mode or the indicator in Preferences takes effect on the next dictation with no
restart, no model reload, and no window where F8 is dead. Changing the model or
device still restarts, as it must.

# Flatpak Backend B integration — design

**Date:** 2026-08-16
**Status:** Approved (design), ready for implementation plan
**Parent effort:** Packaging → Phase 3 (Flatpak). Sub-project #1 of the "real Flatpak"
decomposition (Backend B integration → manifest → onboarding → GPU add-on → Flathub).
Builds directly on the proven portal-input spike — see
`spikes/flatpak-portal/FINDINGS.md` and Obsidian
*"2026-08-16 - Flatpak portal spike results"*.

## Purpose

Let TalkType's dictation work inside a Flatpak sandbox, where the current input
mechanisms are blocked. Do it by adding a **second, swappable input/output
backend** chosen at startup — never by changing the mechanisms that already
work everywhere else.

- **Backend A** (all non-Flatpak installs): evdev hotkey + ydotool typing —
  **unchanged**.
- **Backend B** (Flatpak): GlobalShortcuts-portal hotkey + RemoteDesktop/libei
  typing — the pieces validated in the spike.
- **Selection:** one check at startup — `os.environ.get("FLATPAK_ID")` set →
  Backend B, else Backend A. Add, don't replace.

**Guarantee this design exists to deliver:** the Flatpak behaves the same for
users as every other install, and every other install is completely unaffected
(a bug in Backend B can only affect the Flatpak).

## Already settled by the spike (not re-decided here)

- **Typing** = RemoteDesktop portal → SelectDevices(KEYBOARD) → Start →
  ConnectToEIS → **libei via ctypes** (`libei.so.1`; no helper binary, no GI).
- **Hotkey** = GlobalShortcuts portal, **one** `dictate` shortcut. It emits both
  `Activated` (press) and `Deactivated` (release), so that single binding covers
  hold-to-talk (start on press / stop on release) AND tap-to-toggle (flip on
  press) — no second shortcut needed.
- **Selection** = `FLATPAK_ID`.
- **Runtime** = `org.gnome.Platform//48` (ships python + PyGObject + Gio typelib
  + libei), so nothing extra is bundled for the input layer.

## Architecture

The recording/transcription core in `app.py` talks to the outside world through
a thin waist:
- **Output:** a single `type_text(text) -> bool` call.
- **Input:** two thread-safe events (`_cmd_start_recording`, `_cmd_stop_recording`)
  that a source sets and the recording logic consumes.

Backend B swaps only what sits *outside* that waist. The core is untouched.

### Components (new, focused modules)

- `output_backends.py`
  - `YdotoolOutputBackend.type_text()` — wraps the existing `_type_text` path.
  - `LibeiOutputBackend.type_text()` — the spike's `type_portal.py` typing,
    productionized: holds one long-lived RemoteDesktop/EIS session + libei
    context and emits keystrokes for the given text.
- `input_backends.py`
  - `EvdevInputBackend` — wraps the existing evdev loop (grab keyboards, keycode
    match, hold/toggle logic); sets the `_cmd_*` events as today.
  - `PortalInputBackend` — creates the GlobalShortcuts session, binds the
    `dictate` shortcut, runs a GLib main loop, and translates
    `Activated`/`Deactivated` into the same `_cmd_*` events. Hold vs toggle is
    decided by the existing `config.mode`.
- `portal_common.py` — the GDBus Request/Response helper + `register_app_id`
  no-op-in-sandbox handling, lifted from the spike's `_portal_common.py`.
- `libei_ctypes.py` — the ctypes wrapper for `libei.so.1` (signatures, enum
  constants, the variadic-`bind_capabilities` fix, keycode mapping), lifted from
  `type_portal.py`.
- `backend_select.py` (or a small function in `app.py`) —
  `select_backends() -> (InputBackend, OutputBackend)` keyed on `FLATPAK_ID`.

`app.py` stays the orchestrator: it asks `select_backends()` for the pair, wires
the input backend to the `_cmd_*` events and the output backend to the
post-transcription `type_text()` call, and runs the recording core as it does now.

## Data flow (Backend B)

1. **Startup:** detect `FLATPAK_ID` → build `PortalInputBackend` +
   `LibeiOutputBackend`.
2. **Input backend:** CreateSession + BindShortcuts(`dictate`) on the
   GlobalShortcuts portal; subscribe to `Activated`/`Deactivated`
   (`sender=None`). On `Activated`: set `_cmd_start_recording` (hold) or flip
   (toggle); on `Deactivated`: set `_cmd_stop_recording` (hold). A GLib main loop
   thread drives these signals.
3. **Recording core (unchanged):** consumes the `_cmd_*` events, records,
   transcribes.
4. **Output backend:** on transcription complete, `type_text(text)` streams the
   keystrokes via libei over the established EIS connection.

## Session / approval lifecycle (Backend B)

- **Typing (RemoteDesktop):** establish the session once — CreateSession →
  SelectDevices(KEYBOARD) → Start (desktop shows the one-time "Allow remote
  control?" dialog) → ConnectToEIS → libei context, kept alive for the service
  lifetime. Request `persist_mode` and store the returned `restore_token` in the
  app data dir so subsequent launches restore the session without re-prompting.
  Establish at service startup (so the first dictation isn't delayed by the
  dialog); if not yet approved, dictation output surfaces a clear "grant remote
  control to type" message rather than failing silently.
- **Hotkey (GlobalShortcuts):** bind at startup. The *key assignment* is
  desktop-owned — GNOME shows a picker; KDE lists the action in System Settings.
  Backend B only registers the `dictate` action and (best-effort) suggests a
  default trigger. Wrapping a friendly explanation around this is the onboarding
  sub-project's job; Backend B just needs the binding to exist.

## Error handling

- Portal/libei unavailable, user denies the remote-control dialog, or libei
  setup fails → log it and surface a plain-language notice ("TalkType needs
  permission to type — your desktop will ask; approve it to dictate"), never a
  silent no-op.
- `restore_token` invalid/expired → fall back to a fresh Start (re-prompt once).
- GlobalShortcuts bind fails → notify that the hotkey couldn't be registered and
  point to desktop shortcut settings.

## Testing

- **Unit-testable (no sandbox):** `select_backends()` returns the right pair for
  `FLATPAK_ID` set/unset; the libei char→evdev-keycode mapping; portal variant
  construction; the `_cmd_*` wiring from a fake Activated/Deactivated.
- **Integration:** extend the throwaway-Flatpak recipe (`build_spike_flatpak.sh`)
  to wrap the **real** TalkType (on `org.gnome.Platform//48`, `finish-args`
  `--socket=wayland --socket=fallback-x11 --share=ipc --socket=pulseaudio`,
  portal access) and dictate end-to-end on **KDE**, then a **GNOME** cross-check.
- **Regression:** the existing non-Flatpak test suite proves Backend A is
  unchanged; a manual dictation on the host confirms evdev/ydotool still work.

## Scope

**In:** the two backend interfaces; Backend A wrappers around the existing code;
Backend B portal implementations (productionized spike code); `FLATPAK_ID`
selection; session lifecycle + restore token; wiring into the recording core;
plain-language error surfacing.

**Out (later sub-projects):** the production Flatpak manifest (bundling
faster-whisper / ctranslate2 / model handling); the polished onboarding UX for
the portal approval + hotkey bind; the GPU/NVIDIA add-on; Flathub submission.
Clipboard/paste is unchanged (`wl-copy` works under `--socket=wayland`).

## Risks carried in

- The recording indicator uses XWayland `gtk_window_move()`; confirm its
  positioning behaves under the sandbox (verify during integration, adjust if
  needed — not a backend concern per se).
- `restore_token` semantics differ slightly across GNOME/KDE portal backends;
  the fresh-Start fallback covers the case where restore fails.

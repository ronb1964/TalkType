# Flatpak portal-input spike — design

**Date:** 2026-08-15
**Status:** Approved (design), ready for implementation plan
**Parent effort:** Packaging expansion → Phase 3 (Flatpak / Flathub). See Obsidian note
*"2026-08-15 - Packaging expansion plan (deb, rpm, Flatpak)"* for the full multi-phase plan.

## Why this exists

TalkType's `.deb`, `.rpm`, and AppImage are not sandboxed, so the three things
the app depends on — **typing into other apps** (`ydotool`), **grabbing a global
hotkey** (`evdev`), and **runtime-downloading NVIDIA/CUDA support** — all work
unchanged. A Flatpak runs in a sandbox that blocks all three. The agreed
architecture (see parent plan) is a **dual-backend input layer**: keep the
current evdev+ydotool path for AppImage/.deb/.rpm ("Backend A"), and add a
**portal-based path ("Backend B")** for the Flatpak, chosen at runtime by
detecting the sandbox (`FLATPAK_ID`).

Backend B is weeks of work and its core mechanism is genuinely unproven **from
Python**. This spike de-risks it: before writing any Flatpak manifest or
refactoring `app.py`, prove that portal-based typing and hotkeys actually work
on the two desktops that matter (KDE Plasma, GNOME), and write down exactly how.

**This spike ships no product code.** Its output is knowledge + throwaway
prototypes. The real Backend B integration is a separate later sub-project.

## Current reality (verified 2026-08-15, with sources)

- The old simple path — `RemoteDesktop` portal `Notify*` D-Bus methods for
  injecting keystrokes — is **deprecated on current GNOME/KDE**. Once an EIS
  connection exists the `Notify*` methods return errors; in practice
  `RemoteDesktop.ConnectToEIS` + **libei/EIS** is the only typing path that
  works on modern KDE Plasma and GNOME.
  ([RemoteDesktop portal docs](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html),
  [who-t, Jul 2026](http://who-t.blogspot.com/2026/07/libei-integrations-in-xdg-remotedesktop.html))
- **libei** is a C (GObject-based) library using a UNIX-socket binary protocol;
  it handles portal negotiation internally. libei portal integration landed in
  xdg-desktop-portal ≥1.21.0 and current-gen GNOME/KDE compositors.
- **No confirmed mature pure-Python libei recipe exists.** This is the spike's
  central unknown.
- The **GlobalShortcuts portal** (pure D-Bus) emits separate `Activated` and
  `Deactivated` signals → hold-to-talk (press/release) and tap-to-toggle both
  map cleanly. Widely supported on GNOME and KDE.
  ([GlobalShortcuts portal docs](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html))

## Goal (success criteria)

On **KDE Plasma (Ron's host)** and a **GNOME VM**, using small standalone
programs that do **not** touch `app.py`:

1. **Typing:** inject the text `hello, world.` (letters + comma + period, since
   dictation output contains punctuation) into a real focused text editor via
   the portal/libei path.
2. **Hotkey:** register a global shortcut through the GlobalShortcuts portal and
   observe **both** press (`Activated`) and release (`Deactivated`) — proving
   hold-to-talk and toggle are both achievable.
3. **Findings written down:** which typing method worked on each desktop, the
   hotkey bind/rebind behaviour per desktop, and a recommended shape for the
   real Backend B.

The spike is "done" when 1–3 are demonstrated on both desktops (or a hard
blocker is documented with evidence).

## Part A — Typing prototype (highest risk)

Reach libei from Python by trying, in order of preference, and record which
works on each desktop:

1. **GObject Introspection** — `gi.repository.Ei` (or equivalent typelib).
   *Preferred:* same mechanism TalkType already uses for GTK, no new dependency
   style. Wins if the libei typelib is present on the system/runtime.
2. **Direct C-library calls** via `ctypes`/`cffi` against `libei.so`.
   Always possible; more manual; no extra runtime component.
3. **Small helper program** (e.g. Rust `reis` or a tiny C libei client) that the
   Python app talks to. Fallback if Python can't drive libei directly; would add
   one bundled component to the eventual Flatpak.

Each attempt must: open a `RemoteDesktop` session, select the keyboard device,
`ConnectToEIS`, and stream the test string to the focused editor.

**Deliverable:** the working prototype(s) + a note of the exact method, library
versions, and any per-desktop quirks (e.g. whether KDE routes via its private
`org.kde.KWin.EIS` interface).

## Part B — Hotkey prototype (lower risk)

Standalone program that:
1. Creates a `GlobalShortcuts` portal session and calls `BindShortcuts`
   (suggesting an F-key default; the **desktop draws its own bind dialog** — we
   cannot skin it; some compositors pre-fill, others require the user to pick).
2. Listens for `Activated` and `Deactivated` and logs both with timestamps,
   proving hold-to-talk (press=start, release=stop) and toggle (press=flip).
3. Notes per desktop whether a **rebind** can be triggered on demand from the
   app, or whether the user must go to system keyboard settings (informs the
   future Preferences "change hotkey" flow).

## Part C — Findings write-up (the real product)

- A spec-folder findings doc + an Obsidian note capturing, per desktop
  (KDE / GNOME): typing method that worked, hotkey press/release behaviour,
  rebind behaviour, library/version notes, and gotchas.
- A **recommendation** for how the real Backend B should be built (which libei
  access method, whether a helper binary is needed, how the sandbox-detection
  switch should select A vs B), feeding the next sub-project.

## Out of scope (each a later sub-project)

- The Flatpak manifest / build / Flathub submission.
- GPU / NVIDIA add-on (deferred per parent plan; CPU-only Flatpak first).
- Refactoring `app.py` to introduce the real Backend A/B seam.
- Onboarding/Preferences UI changes for the portal hotkey flow.
- **Clipboard / paste mode:** low risk (own-set clipboard + `wl-copy` work under
  Flatpak). A ~5-minute confirmation only, not a build.

## Notes / constraints

- Prototypes live outside the app (e.g. a `spikes/flatpak-portal/` scratch area
  or the session scratchpad) and are **not** wired into `app.py`, the tray, or
  the build. They are disposable.
- Run tests against real focused apps on each desktop; a headless container
  cannot validate input injection.
- Keep everything behind the parent plan's **add-don't-replace** rule: Backend A
  (evdev+ydotool) stays as the universal fallback regardless of spike outcome.

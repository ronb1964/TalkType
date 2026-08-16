# TalkType Flatpak (self-hosted) — design

**Date:** 2026-08-16 · **Status:** approved (brainstorm) · **Branch:** `flatpak-manifest`
**Depends on:** Backend B seam (`flatpak-backend-b`) + both de-risking spikes (portal input, GPU).

## Goal

A real, self-hosted Flatpak of TalkType that a user installs directly (a `.flatpak` bundle / small
user repo) and that **operates and looks the same as the AppImage** — including GPU acceleration.
Distribution is self-hosted first; Flathub is a later, separate effort. No remaining research risk:
both sandbox unknowns are settled by the spikes. This project is assembly + UX-parity polish.

### Success criteria
- `flatpak run io.github.ronb1964.TalkType` starts the tray + dictation service in the sandbox.
- Hold-to-talk dictates via **Backend B** (GlobalShortcuts portal → libei typing), selected because
  `FLATPAK_ID` is set — evdev/ydotool (Backend A) is never used inside the Flatpak.
- First run offers the CUDA download (NVIDIA detected) and, after it, transcribes on the **GPU** —
  same flow and speed character as the AppImage.
- Model download, preferences, recording indicator, notifications, About/Help all behave like the
  AppImage.
- Works on **KDE and GNOME** (the two VMs), Wayland.
- Built reproducibly by a committed `flatpak-builder` manifest; produces a `.flatpak` bundle.

### Non-goals
- Flathub submission and its stricter rules (later).
- Changing Backend A or any non-Flatpak packaging (AppImage/.deb/.rpm/AUR stay as-is).
- NVIDIA support for non-NVIDIA GPUs (AMD/Intel) beyond CPU — matches current app scope.

## Architecture — what changes vs the AppImage

The **same source** runs; the Flatpak differs only in packaging and in the two already-built
`FLATPAK_ID`-gated seams. Concretely, the manifest must provide what `org.gnome.Platform//48`
(Python 3.12) lacks, and the app must branch on `FLATPAK_ID` for the handful of host-specific bits.

### 1. Runtime base + GI
- Base: `org.gnome.Platform//48`, built with `org.gnome.Sdk//48`.
- Provided by the runtime (verify at build): Gtk 3.0, Gdk 3.0, GdkPixbuf, Gio, `Notify` (libnotify),
  `Atspi`. **Bundle:** `libayatana-appindicator3` + its GI typelib (tray icon) — not in the runtime.

### 2. Python dependencies (pip modules in the manifest, Python 3.12)
`faster-whisper` (→ `ctranslate2 4.x`, `av`, `onnxruntime`, `huggingface_hub`, `tokenizers`,
`numpy`), `sounddevice`, `evdev`, `pyperclip`, `toml`. Installed into `/app` via flatpak-builder
`pip3 install` modules (proven working in the GPU spike). PyGObject/pycairo come from the runtime.

### 3. Native libraries to bundle
- **PortAudio** (`libportaudio.so.2`) — `sounddevice` dlopens it at import; not in the runtime.
- **wl-clipboard** (`wl-copy`/`wl-paste`) — used for paste-mode clipboard; not in the runtime.
  (Alternative considered: the clipboard portal — deferred; bundling wl-clipboard matches current
  behavior with least code change.)

### 4. Input/output backends (already built, `FLATPAK_ID`-gated)
- Input: `PortalInputBackend` (GlobalShortcuts). Output: `LibeiOutputBackend` (RemoteDesktop→libei).
- No evdev grab, no ydotool, no `wtype` in the sandbox.

### 5. GPU / CUDA (download-on-demand, adapted for the sandbox)
- Keep the AppImage model: detect NVIDIA → offer ~1.4 GB CUDA download → store in the app data dir
  (`~/.var/app/io.github.ronb1964.TalkType/data/.../cuda`) → add its `cudnn/lib`, `cublas/lib`,
  `cuda_runtime/lib` to `LD_LIBRARY_PATH`. `libcuda` comes from the NVIDIA GL extension (spike).
- **Detection:** replace `nvidia-smi` (absent in sandbox) with a Flatpak-aware check —
  `ctranslate2.get_cuda_device_count()` (once bundled) or the ctypes `libcuda` probe from the spike.
  Gate the change on `FLATPAK_ID` so Backend A's detection is untouched.
- `finish-args: --device=dri` (minimal; proven sufficient in the GPU spike).

### 6. Behavior parity toggles (gated on `FLATPAK_ID`)
- **Updater:** disable the in-app updater and hide "Check for Updates" — Flatpak updates via
  `flatpak update`. (The 0.7.1 updater is install-type-aware already; add a Flatpak branch that
  no-ops / points at `flatpak update`.)
- **Onboarding:** the hotkey is assigned by the desktop, not the app. First-run must explain "your
  desktop will ask you to set the dictation shortcut" — KDE: System Settings → Shortcuts; GNOME: the
  picker. Everything else (model choice, CUDA offer, mic test) stays as-is.
- **Tray/desktop integration:** ship the `.desktop`, icons, and the existing
  `io.github.ronb1964.TalkType.appdata.xml` (AppStream) in the manifest.

### 7. finish-args (starting set)
`--socket=wayland --socket=fallback-x11 --share=ipc --socket=pulseaudio --device=dri
--share=network --talk-name=org.freedesktop.portal.Desktop`
(network for model/CUDA downloads; fallback-x11 for the recording indicator's `gtk_window_move`;
pulseaudio for mic capture; portal talk-name for GlobalShortcuts + RemoteDesktop.)

## Build phases (ordered; each independently verifiable)

1. **Boot skeleton** — manifest builds `org.gnome.Platform//48` + all Python deps + PortAudio +
   AppIndicator; the app *imports and starts* in the sandbox (tray + service), CPU-only, model
   download works. Proves the dependency bundle. *Verify: tray appears, service logs "Model loaded".*
2. **Backend B end-to-end (KDE)** — assign the shortcut, approve the remote-control dialog, dictate
   into an editor via libei. *Verify: hold-to-talk types text; Backend A code never runs.*
3. **GPU parity** — wire download-on-demand CUDA into the app data dir + `FLATPAK_ID` detection
   swap; confirm GPU transcription. *Verify: `device=cuda`, no CPU fallback, fast.*
4. **UX parity** — updater no-op in Flatpak, onboarding hotkey guidance, indicator position,
   notifications, clipboard/paste, Help/About text. *Verify: first-run + menus match the AppImage.*
5. **GNOME cross-check** — repeat 2–4 in the GNOME VM (picker instead of System Settings).
   *Verify: parity on GNOME; record diffs.*
6. **Package + distribute** — produce a `.flatpak` single-file bundle + a `build-flatpak.sh` that
   mirrors `build-release.sh`; document install. *Verify: fresh install from the bundle runs.*

## Testing
- Unit tests already cover the Backend B seam + `FLATPAK_ID` selection (589 passing); add tests for
  any new `FLATPAK_ID` branches (updater no-op, GPU detection swap) following the existing pattern.
- Integration is manual-in-sandbox per phase above (KDE then GNOME), like the spikes.

## Open items to settle during the build (not research risk — assembly choices)
- Where to source `libayatana-appindicator3` + typelib in the manifest (build from source vs a
  reliable module snippet) and confirm the runtime ships its GI deps (Dbusmenu).
- Confirm the runtime provides `Atspi`/`Notify` typelibs; bundle if not.
- Recording-indicator positioning under the sandbox (open risk carried from the portal spike).
- `restore_token` storage location for the RemoteDesktop session inside the sandbox data dir.

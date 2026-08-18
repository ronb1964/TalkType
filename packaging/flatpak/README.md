# TalkType — Flatpak

A self-hosted [Flatpak](https://flatpak.org/) build of TalkType. It runs the same
app as the AppImage/`.deb`/`.rpm`, but sandboxed: dictation hotkeys go through the
desktop's **GlobalShortcuts portal** and typing through **libei** (Backend B), so
there is no `ydotool`, no `uinput`, no `input` group, and no root.

App ID: **`io.github.ronb1964.TalkType`** · Runtime: **`org.gnome.Platform//50`**

## Requirements

- A desktop whose portal implements **GlobalShortcuts** — **GNOME** (45+) or
  **KDE Plasma 6**. Both were validated (GNOME on Ubuntu 26.04, KDE on Fedora/Nobara).
- **XFCE, Cinnamon, and MATE do _not_ implement that portal** — the hotkey can't be
  registered there. Use the AppImage, `.deb`, `.rpm`, or AUR package instead. (The
  onboarding screen detects this and says so.)
- `flatpak`, plus the **Flathub** remote for the GNOME runtime the bundle depends on:

  ```bash
  flatpak remote-add --if-not-exists --user flathub https://dl.flathub.org/repo/flathub.flatpakrepo
  ```

## Install (from a release bundle)

```bash
# optional: verify the download first
sha256sum -c TalkType-flatpak-*.flatpak.sha256

flatpak install --user ./TalkType-flatpak-*.flatpak
flatpak run io.github.ronb1964.TalkType
```

The runtime (`org.gnome.Platform//50`) is pulled from Flathub automatically on first
install if it isn't already present.

### First run

- Onboarding is **desktop-aware**. It walks you through assigning a dictation key:
  - **KDE** — assign it in System Settings → Keyboard → Shortcuts (or the inline
    chooser that appears the first time).
  - **GNOME** — a native **"Add Keyboard Shortcuts"** dialog pops up; click the pencil
    on each shortcut, allow it, press your key, and click **Add**.
- The **first time you dictate**, the desktop asks permission to type into other apps
  (the Remote Desktop portal). Approve it once. On GNOME, turn **on** the
  **"Allow Remote Interaction"** switch before clicking **Share**.
- **NVIDIA GPU** acceleration is optional and downloaded on demand into the app's data
  dir the first time you enable it — nothing GPU-related ships in the bundle.

### Updates

Flatpak apps update through Flatpak: `flatpak update io.github.ronb1964.TalkType`.
TalkType's built-in update check is Flatpak-aware and will point you at that command
rather than trying to install an AppImage.

## Build from source

Uses `flatpak-builder` run as the `org.flatpak.Builder` Flatpak, so no system package
is needed:

```bash
flatpak install --user -y flathub org.flatpak.Builder   # one-time

# build + install --user
./packaging/flatpak/build-flatpak.sh

# build + install, and also emit a single-file bundle + SHA256 sidecar
./packaging/flatpak/build-flatpak.sh bundle
# -> TalkType-flatpak-<version>.flatpak
# -> TalkType-flatpak-<version>.flatpak.sha256
```

Build artifacts (`.flatpak-build/`, `.flatpak-builder/`, `.flatpak-repo/`, and the
`*.flatpak` bundles) are git-ignored.

## What's in here

| File | Purpose |
|------|---------|
| `io.github.ronb1964.TalkType.yml` | flatpak-builder manifest (runtime, deps, finish-args) |
| `io.github.ronb1964.TalkType.svg` | square app icon installed into the sandbox |
| `talktype-launcher` | in-sandbox entry point (sets `PYTHONPATH`, runs `-m talktype.tray`) |
| `build-flatpak.sh` | build + install (+ optional `bundle`) wrapper |
| `shared-modules/` | vendored Flathub modules — `libayatana-appindicator` (tray) + `intltool` |

The manifest bundles what the GNOME runtime lacks: the Python ML/audio stack
(faster-whisper, sounddevice, PortAudio, numpy, evdev, dbus-python) and
`libayatana-appindicator` for the tray. The app itself branches on `FLATPAK_ID` only
at two seams — the portal hotkey (input) and libei typing (output); everything else is
the same code as the other packages.

## Uninstall

```bash
flatpak uninstall --user io.github.ronb1964.TalkType
```

Your settings and downloaded models live under
`~/.var/app/io.github.ronb1964.TalkType/`; add `--delete-data` to remove those too.

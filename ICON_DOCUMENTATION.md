# TalkType Icon Documentation

## Official Icon

The **OFFICIAL** TalkType icon is:
- **Source:** `icons/TT_retro_square_light.svg`
- **Protected backup:** `icons/OFFICIAL_ICON_DO_NOT_CHANGE.svg` (read-only)

This is the retro square design with the "TT" text and "TALKTYPE" wordmark in blue (#3aa8ff) on a white background.

## ⚠️ IMPORTANT: DO NOT CHANGE THE ICON

The icon file `io.github.ronb1964.TalkType.svg` at the project root is the canonical icon used by:
- Development desktop launcher (`~/.local/share/applications/talktype-dev.desktop`)
- AppImage builds (all build scripts)
- Desktop entries
- AppStream metadata

**This icon must ALWAYS be the retro square light design.**

## Icon Locations

### Source Icon (Canonical)
- `icons/TT_retro_square_light.svg` - The original master copy
- `icons/OFFICIAL_ICON_DO_NOT_CHANGE.svg` - Read-only backup (DO NOT MODIFY)

### Active Icon (Used by builds)
- `io.github.ronb1964.TalkType.svg` - **MUST** always be a copy of the official icon

### Build Artifacts
- `AppDir/io.github.ronb1964.TalkType.svg` - Copied during AppImage build
- `AppDir/.DirIcon` - Copied during AppImage build
- `AppDir/usr/share/icons/hicolor/scalable/apps/io.github.ronb1964.TalkType.svg` - Copied during build

### Desktop Launchers
- `~/.local/share/applications/talktype-dev.desktop` - Points to `io.github.ronb1964.TalkType.svg`
- `io.github.ronb1964.TalkType.desktop` - References icon by name

## How to Restore the Correct Icon

If the icon ever gets changed accidentally, restore it with:

```bash
cp icons/OFFICIAL_ICON_DO_NOT_CHANGE.svg io.github.ronb1964.TalkType.svg
```

Or from the original source:

```bash
cp icons/TT_retro_square_light.svg io.github.ronb1964.TalkType.svg
```

Then update AppDir if it exists:

```bash
if [ -d AppDir ]; then
    cp io.github.ronb1964.TalkType.svg AppDir/io.github.ronb1964.TalkType.svg
    cp io.github.ronb1964.TalkType.svg AppDir/.DirIcon
    mkdir -p AppDir/usr/share/icons/hicolor/scalable/apps
    cp io.github.ronb1964.TalkType.svg AppDir/usr/share/icons/hicolor/scalable/apps/
fi
```

And refresh the icon cache:

```bash
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor/ 2>/dev/null || true
```

## Build Script Verification

All AppImage build scripts (`build-appimage-*.sh`) copy the icon from:
- `io.github.ronb1964.TalkType.svg` → `AppDir/io.github.ronb1964.TalkType.svg`
- `io.github.ronb1964.TalkType.svg` → `AppDir/.DirIcon`
- `io.github.ronb1964.TalkType.svg` → `AppDir/usr/share/icons/hicolor/scalable/apps/`

This happens automatically on every build at these lines in `build-appimage-cpu.sh`:
- Line 274-280: Icon file copying

## Other Icon Files (Unused)

These icon files exist in the repo but are NOT used:
- `talktype-icon-new.svg` - Old design
- `talktype-icon-v2.svg` - Old design
- `talktype-icon-v3.svg` - Old design
- `icons/TT_retro_square_light-Inkscape.svg` - Inkscape working file
- Various PNG files in `icons/` - Rasterized versions

## Summary

**Always use:** `icons/TT_retro_square_light.svg` (the retro square light design)

**Never change:** `io.github.ronb1964.TalkType.svg` unless replacing with the official icon

**Backup:** `icons/OFFICIAL_ICON_DO_NOT_CHANGE.svg` (protected read-only copy)

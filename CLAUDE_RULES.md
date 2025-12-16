# CRITICAL RULES - READ EVERY SESSION

## RON'S DAILY SETUP - DO NOT CHANGE

**Ron uses the DEVELOPMENT VERSION day-to-day, NOT the AppImage.**

### Development Version Requirements:
- **Desktop launcher**: "TalkType (Dev)" in `~/.local/share/applications/talktype-dev.desktop`
- **Autostart**: Must launch the dev version, NOT the AppImage
- **DEV_MODE=1**: Must be set to show BOTH tray icons (GTK tray + GNOME extension)
- **Both icons visible**: In dev mode, Ron needs to see both the GTK tray icon AND the GNOME shell extension icon for testing

### Autostart Configuration (MUST be dev version):
```
Exec=env GDK_BACKEND=x11 DEV_MODE=1 PYTHONPATH=/home/ron/Projects/TalkType/src:/usr/lib64/python3.14/site-packages:/usr/lib/python3.14/site-packages /home/ron/Projects/TalkType/.venv/bin/python -m talktype.tray
```

Note: `GDK_BACKEND=x11` forces XWayland mode, which enables recording indicator positioning on Wayland.

### AppImage is ONLY for:
- Testing before release
- Distribution to other users
- NEVER for Ron's daily use

### NEVER damage or delete:
- The `.venv/` directory (contains all dependencies)
- The `src/talktype/` directory (source code)
- The development desktop launcher
- Ron's config files without explicit permission

---

## NEVER RUN DESTRUCTIVE COMMANDS WITHOUT EXPLICIT USER PERMISSION

**DESTRUCTIVE COMMANDS INCLUDE:**
- `./fresh-start-dev.sh` - Deletes all dev config, data, models
- `./fresh-start-for-testing.sh` - Deletes AppImage config/data
- Any `rm -rf` commands
- `gsettings set` - Modifying GNOME settings
- Any script that deletes user files, configs, or data

**BEFORE running ANY destructive command:**
1. ASK: "I need to run [COMMAND] which will [EXPLAIN]. Is that okay?"
2. WAIT for explicit "yes" or "go ahead"
3. ONLY THEN proceed

**Exception:** User explicitly requested it in their current message

**REMEMBER: PRESERVE USER DATA ABOVE ALL ELSE**

---

## RELEASE CHECKLIST - NEVER SKIP

When creating a GitHub release, you MUST include:

1. **AppImage**: `TalkType-vX.X.X-x86_64.AppImage`
2. **GNOME Extension**: `talktype-gnome-extension.zip`

The GNOME extension is downloaded from GitHub by users - it is NOT bundled in the AppImage. If you forget to upload it, users will get a 404 error on first run.

**Before creating a release:**
```bash
# 1. Package the extension (if source changed)
./package-extension.sh

# 2. Build the AppImage
./build-release.sh

# 3. Create release with BOTH files
gh release create vX.X.X TalkType-vX.X.X-x86_64.AppImage talktype-gnome-extension.zip --title "..." --notes "..."
```

**NEVER create a release without the extension zip.**

---

## GTK TRAY AND GNOME EXTENSION - KEEP IN SYNC

**TalkType has TWO user interfaces that must stay synchronized:**

1. **GTK Tray Icon** (`src/talktype/tray.py`) - For all Linux desktops
2. **GNOME Shell Extension** (`gnome-extension/talktype@ronb1964.github.io/extension.js`) - For GNOME users

**When adding/modifying menu items or features:**
- Add to BOTH the GTK tray menu AND the GNOME extension menu
- Keep menu order identical between both
- If adding a D-Bus method, update:
  1. `src/talktype/dbus_service.py` - Add the D-Bus method
  2. `src/talktype/tray.py` - Add method to `TrayAppInstance` class
  3. `gnome-extension/.../extension.js` - Add to D-Bus interface AND menu

**Current menu order (must match in both):**
```
Start/Stop Dictation (toggle)
─────────────────────
Active Model: [model]
Device: [device]
Performance ▸
Text Injection Mode ▸
─────────────────────
Preferences...
Help...
About TalkType...
Check for Updates...
─────────────────────
Quit TalkType
```

**Goal:** Users should have the same experience whether using the GTK tray or GNOME extension.
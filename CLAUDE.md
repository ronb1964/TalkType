# TalkType Project Rules for Claude

**READ THIS ENTIRE FILE BEFORE DOING ANYTHING. THESE RULES ARE MANDATORY.**

---

## STOP — MANDATORY RELEASE PROCESS

**You MUST follow this exact sequence. No skipping steps. No exceptions.**

### Step 1: Code Changes
- Make and test code changes in `/home/ron/Projects/TalkType/src/`
- NEVER edit files in `.claude/worktrees/` — Ron's dev version runs from the main project

### Step 2: Ask Before Building
- **NEVER run `./build-release.sh` without asking Ron first**
- Say: "Ready to build the AppImage?" and WAIT for confirmation
- There may be other fixes needed. Don't assume the work is done.

### Step 3: Build the AppImage
```bash
cd /home/ron/Projects/TalkType
./build-release.sh
```

### Step 4: Copy to ~/AppImages/
```bash
cp TalkType-v*.AppImage ~/AppImages/
chmod +x ~/AppImages/TalkType-v*.AppImage
```

### Step 5: Ask Permission for Fresh Start
- Say: "I need to run `./fresh-start-for-testing.sh` which will kill all TalkType processes, remove AppImage config/data, CUDA libs, cached models, and the GNOME extension. Your dev environment stays untouched. Is that okay?"
- WAIT for explicit "yes" or "go ahead"

### Step 6: Run Fresh Start and Verify
```bash
cd /home/ron/Projects/TalkType
./fresh-start-for-testing.sh
```
- Check that ALL items show "✓ Removed" in the output
- Show Ron the AppImage file size (must be under 1GB)

### Step 7: Launch the AppImage from a Terminal (Claude runs this)
- **Claude MUST launch the AppImage using the Bash tool** so terminal output is visible
- NEVER give Ron a command to run himself — Claude launches it directly
- **ALWAYS launch to a log file AND monitor it** — this is a hard requirement, not optional
- Launch in background and capture output:
```bash
cd ~/AppImages && env -u GDK_BACKEND ./TalkType-vX.X.X-x86_64.AppImage > /tmp/talktype-output.log 2>&1 &
```
- Then tail the log to confirm startup:
```bash
sleep 3 && cat /tmp/talktype-output.log
```
- Continue monitoring output as Ron tests — check the log after each reported issue

### Step 8: Ron Tests — WAIT for Results
Ron tests against this checklist. Do NOT proceed until he reports back:
- [ ] Welcome screen appears on first launch
- [ ] GPU detection works and offers CUDA download
- [ ] CUDA download shows progress bar
- [ ] After CUDA download, green checkmark appears immediately
- [ ] Device auto-switches to "cuda" after CUDA download
- [ ] Model downloads show progress bars
- [ ] Default settings are correct (auto_period=True, auto_timeout=5min, language_mode=auto)
- [ ] Dictation works in CPU mode
- [ ] Dictation works in GPU mode after CUDA download
- [ ] Auto-punctuation works consistently
- [ ] Start/stop beeps play
- [ ] Preferences mic test works (level meter, record, replay)

### Step 9: Fix and Rebuild if Needed
If ANY test fails: fix the issue, go back to Step 2, and repeat.

### Step 10: Package the GNOME Extension and the distro packages
```bash
./package-extension.sh
./build-deb.sh
./build-rpm.sh
```

Both `build-deb.sh` and `build-rpm.sh` take no arguments — they read the
version from `pyproject.toml` and repackage the **already-built, already-tested**
AppImage, so they must run AFTER Step 3 and after Ron approves in Step 8.
They need `fpm` installed (`gem install --user-install fpm`); the .rpm also
needs `rpmbuild`.

Order among these three does not matter — each one removes only its OWN line
from `SHA256SUMS.txt` and appends a fresh one. But `./build-release.sh` DELETES
`SHA256SUMS.txt` and regenerates it from scratch, so re-running it (Step 9)
after this step silently drops the .deb and .rpm checksums. If you go back to
Step 2 for a fix, re-run all of Step 10 afterwards.

### Step 11: Commit, Push, and Create GitHub Release
```bash
git add <changed files>
git commit -m "..."
git push
gh release create vX.X.X \
  TalkType-vX.X.X-x86_64.AppImage \
  talktype_X.X.X_amd64.deb \
  talktype-X.X.X-1.x86_64.rpm \
  talktype-gnome-extension.zip \
  SHA256SUMS.txt \
  --title "..." --notes "..."
```

Note the .deb and .rpm use the bare version (`0.7.2`), NOT the `v` prefix the
tag and AppImage use.

**NEVER create a GitHub release without the .deb and .rpm.**
They are how every Debian/Ubuntu/Mint and Fedora/RHEL user installs. Omitting
them ships an AppImage-only release and silently strands those users.

**NEVER create a GitHub release without the GNOME extension zip.**
The extension is downloaded from GitHub by users — if you forget it, users get a 404 error on first run.

**ALWAYS include SHA256SUMS.txt in the release** (generated automatically by
`./build-release.sh` and updated by `./package-extension.sh`). The in-app
updater downloads it to verify the AppImage before installing — without it,
updates still work but skip the integrity check.

**NEVER create a GitHub release before Ron has tested and approved.**

**ALWAYS end the release notes with the AUR vote ask.** The release page is
where people already have installing on their mind, so it converts far better
than the README does. Use this line verbatim:

```
Using TalkType on Arch? A [vote on the AUR page](https://aur.archlinux.org/packages/talktype-appimage) helps other Arch users find it.
```

AUR votes only move when asked for — the package sat at zero from December
2025 to at least August 2026 while still being installed regularly.

---

## DESTRUCTIVE COMMANDS — ALWAYS ASK FIRST

**BEFORE running ANY of these, ASK and WAIT for permission:**
- `./fresh-start-dev.sh` — Deletes all dev config, data, models
- `./fresh-start-for-testing.sh` — Deletes AppImage config/data
- Any `rm -rf` commands
- `gsettings set` — Modifying GNOME settings
- Any script that deletes user files, configs, or data

**Format:** "I need to run [COMMAND] which will [EXPLAIN WHAT IT DELETES]. Is that okay?"

**Exception:** Ron explicitly requested it in his current message.

**PRESERVE USER DATA ABOVE ALL ELSE.**

---

## RON'S DAILY SETUP — DO NOT CHANGE

**Ron uses the DEVELOPMENT VERSION day-to-day, NOT the AppImage.**

### Development Version:
- **Desktop launcher**: "TalkType (Dev)" in `~/.local/share/applications/talktype-dev.desktop`
- **Autostart**: Launches the dev version, NOT the AppImage
- **DEV_MODE=1**: Shows BOTH tray icons (GTK tray + GNOME extension)
- **Source code**: `/home/ron/Projects/TalkType/src/talktype/`

### Autostart Configuration:
```
Exec=env DEV_MODE=1 PYTHONPATH=/home/ron/Projects/TalkType/src:/usr/lib64/python3.14/site-packages:/usr/lib/python3.14/site-packages /home/ron/Projects/TalkType/.venv/bin/python -m talktype.tray
```

### NEVER set GDK_BACKEND when launching the tray

Do not add `GDK_BACKEND=x11` to the launcher, the autostart file, `run-dev.sh`,
the AppImage's AppRun, or a test command — it was there for years and had to be
removed in v0.6.0.

Under XWayland a GTK3 combo popup does not stay open on a plain click; it only
responds to press-drag-release. That made **every dropdown in the app unusable**,
including the model picker on the first-run setup screen.

The recording indicator genuinely does need XWayland (`gtk_window_move()` is
honoured there and ignored on native Wayland, which centres the window). The
tray therefore sets it for the dictation service **alone**, in `tray.py`'s
`_launch_service()`. `tests/test_gdk_backend_scope.py` fails if it is ever set
globally again.

### AppImage is ONLY for:
- Testing before release
- Distribution to other users
- NEVER for Ron's daily use

### NEVER damage or delete:
- The `.venv/` directory
- The `src/talktype/` directory
- The development desktop launcher
- Ron's config files without explicit permission

---

## GTK TRAY AND GNOME EXTENSION — KEEP IN SYNC

TalkType has TWO user interfaces that must stay synchronized:

1. **GTK Tray Icon** (`src/talktype/tray.py`) — For all Linux desktops
2. **GNOME Shell Extension** (`gnome-extension/talktype@ronb1964.github.io/extension.js`) — For GNOME users

**When adding/modifying menu items or features:**
- Add to BOTH the GTK tray menu AND the GNOME extension menu
- Keep menu order identical between both
- If adding a D-Bus method, update:
  1. `src/talktype/dbus_service.py` — Add the D-Bus method
  2. `src/talktype/tray.py` — Add method to `TrayAppInstance` class
  3. `gnome-extension/.../extension.js` — Add to D-Bus interface AND menu

**Menu order (must match in both):**
```
Dictation Service (toggle)
Restart Service
─────────────────────
Active Model: [model]
Device: [device]
Performance ▸
Text Injection Mode ▸
─────────────────────
Preferences...
Voice Commands...
Help...
About TalkType...
Check for Updates...
─────────────────────
Quit TalkType
```

---

## WORKING STYLE

Explain what code does in plain language. Always:
- Provide exact copy/paste commands (include `cd` commands)
- Be direct and honest
- Never assume the reader will debug code themselves

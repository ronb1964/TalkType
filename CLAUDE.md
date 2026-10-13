# TuxTalk Project Rules for Claude

**The app was renamed from TalkType to TuxTalk in 0.15.0** ("TALKTYPE" is
another company's registered trademark for dictation software). Some names
deliberately stay TalkType because changing them would hurt users:
- the project folder `/home/ron/Projects/TalkType` and its `.venv`;
- the GNOME extension UUID `talktype@ronb1964.github.io` and its schema (a new
  UUID is a new extension: a logout and enabling it again);
- the D-Bus name, path and interface `io.github.ronb1964.TalkType` (an old,
  still-loaded extension calls them until the next logout);
- the runtime lock files (an old TalkType and TuxTalk must never run at once);
- the Vulkan engine's `talktype-whisper-vulkan-*` release files (already published);
- the compatibility copies in every release: `TalkType-vX.X.X-x86_64.AppImage.zsync`
  and `talktype-gnome-extension.zip` (0.14.x installs look for those names).
Old folders, launchers and KDE shortcuts are moved or cleaned on start by
`src/tuxtalk/rename_migration.py`. Plan: `docs/superpowers/plans/2026-10-11-rename-to-tuxtalk.md`.

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
cp TuxTalk-v*.AppImage ~/AppImages/
chmod +x ~/AppImages/TuxTalk-v*.AppImage
```

### Step 5: Ask Permission for Fresh Start
- Say: "I need to run `./fresh-start-for-testing.sh` which will kill all TuxTalk processes, remove AppImage config/data, CUDA libs, cached models, and the GNOME extension. Your dev environment stays untouched. Is that okay?"
- WAIT for explicit "yes" or "go ahead"

### Step 6: Run Fresh Start and Verify
```bash
cd /home/ron/Projects/TalkType
./fresh-start-for-testing.sh
```
- Check that ALL items show "✓ Removed" in the output, including
  "✓ TuxTalk models removed". Since 0.14.2 the script clears Parakeet, the
  Vulkan models and the AI model too, so first run really downloads them
- Show Ron the AppImage file size (must be under 1GB)

### Step 7: Launch the AppImage from a Terminal (Claude runs this)
- **Claude MUST launch the AppImage using the Bash tool** so terminal output is visible
- NEVER give Ron a command to run himself — Claude launches it directly
- **ALWAYS launch to a log file AND monitor it** — this is a hard requirement, not optional
- Launch in background and capture output:
```bash
cd ~/AppImages && env -u GDK_BACKEND ./TuxTalk-vX.X.X-x86_64.AppImage > /tmp/tuxtalk-output.log 2>&1 &
```
- Then tail the log to confirm startup:
```bash
sleep 3 && cat /tmp/tuxtalk-output.log
```
- Continue monitoring output as Ron tests — check the log after each reported issue

### Step 8: Ron Tests — WAIT for Results
Ron tests against this checklist. Do NOT proceed until he reports back.
Claude checks every item against the log too
(`~/.config/tuxtalk/tuxtalk.log`), not only Ron's report. In 0.14.1 the
"GPU" test had really run on the processor.

First run (since 0.14.2 it recommends one setup; CUDA is not offered here):
- [ ] Welcome screen appears, and its card names the graphics card and language ("Parakeet on your NVIDIA ..., For English")
- [ ] Other options: changing the language, model or graphics-card tickbox updates the card and its download size
- [ ] Hotkey test, then the tips screen (no model picker)
- [ ] Downloads show progress bars: the Vulkan engine and Parakeet for the graphics card. The log must show a real download, not "cached"
- [ ] The speed check runs, and the log shows its result (`Speed check (parakeet-v3): graphics …s, processor …s`)
- [ ] Default settings are correct (model=parakeet-v3, device=vulkan when the card won, auto_period=True, auto_timeout 5 min, language_mode=auto)
- [ ] Dictation works on the graphics card (log: `Parakeet on GPU`)

Preferences and the rest:
- [ ] Dictation works in CPU mode (Device → CPU downloads the processor copy of Parakeet with a progress bar)
- [ ] CUDA: Preferences → General → Device lists "CUDA (1.4 GB download, …)" on NVIDIA before anything is downloaded. Picking it asks, then shows a progress bar, then "Downloaded!". On Parakeet it then asks which Whisper model to use on CUDA, Large-v3 preselected (Keep Parakeet changes nothing, and the dropdown goes back); on a Whisper model it switches to "cuda" by itself. Either switch restarts dictation onto CUDA (check the log). Advanced shows only the status line
- [ ] With Parakeet selected, the CUDA entry reads "CUDA (Parakeet runs on the processor)" and the warning under the settings is amber and bold
- [ ] Dictation works on CUDA with a Whisper model (e.g. small)
- [ ] AI self-corrections: turning it on downloads the model; "meet at three, no wait, four" types "meet at four"
- [ ] Auto-punctuation works consistently
- [ ] Hands-free: double-tap F9 and say nothing. It stops by itself after 10 seconds with the cancel beep and types nothing (log: "Auto-stop: nothing said"). With the bars indicator, the bars stay low while it's quiet
- [ ] Start/stop beeps play
- [ ] With a YouTube video playing, dictating pauses it and it plays again after (log: "Paused … while dictating", "Resumed …"). A video that was already paused stays paused. Preferences → "Pause music and videos while dictating" off: nothing pauses
- [ ] Preferences mic test works (level meter, record, replay)
- [ ] TuxTalk Labs: Preferences → Advanced ends with the Labs section (note, Voice editing, How these work, Send feedback). How these work opens Help on the TuxTalk Labs tab; Send feedback opens Discussions
- [ ] Voice editing: Preferences → Advanced → TuxTalk Labs → Voice editing (downloads the AI if self-corrections hasn't). In KWrite select a sentence, hold Shift+F8, say "make this more formal": the selection is replaced, Ctrl+Z restores it, and the clipboard still holds what it held before (log: "Voice edit:"). Nothing selected: the notice says to select text first. Shift+F9 tap-to-start/stop works too. With it off, Shift+F8 dictates normally
- [ ] Paste Last Dictation: dictate, click into another window, press Ctrl+Alt+P. The same text is typed there once the keys are let go, with no stray Ctrl+Alt shortcut (log: "Paste last dictation"). Preferences → General → Paste Last Dictation: None turns it off
- [ ] Your Words: Preferences → Snippets → Your Words..., add "TuxTalk", Save. On Parakeet, saying "tux talk" types TuxTalk. On a Whisper model (e.g. small) the name comes out right more often (log: "Loaded your words" / "Reloaded your words"). Saying nothing with a Whisper model types nothing
- [ ] Tray → Performance shows Recommended / Lightest / Battery saver, with the dot on the active one
- [ ] Preferences → General: off the recommended setup, the row says "Recommended for this computer: …" with Use Recommended, which sets Model and Device (Vulkan: download and speed check first) and turns into "✓ You're on the recommended setup". "What works with what?" shows the models-by-device grid and a line about this computer
- [ ] Backup: Preferences → Updates & Backup fits without scrolling. Save Backup opens the desktop's file dialog, writes the .zip, and "Last saved" turns from amber "never" to the date. Change the hotkey, then Load Backup puts it back, restarts dictation (log) and closes Preferences. Earlier settings lists both "— your backup" files from the backup folder and "— automatic" copies, newest first, and Restore undoes the load. A second backup the same day gets its own name (the time is in it). A non-backup file is turned away with a message. Backup folder → Change… opens a folder browser; after picking one, Save Backup and Load Backup open in it. Tray → Check for Updates still opens this tab
- [ ] F8 and F9 leave no stray character in a terminal (KDE and GNOME)
- [ ] Hotkeys: the dropdowns label F1, F5, F11 and F12 with what apps use them for. Change the hold key and click Apply: "Try your new hotkey?" replaces "Settings applied", and Test Now opens the hotkey test. On KDE, pick a key KDE already uses and the question says so (log: "KDE already uses …")

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
  TuxTalk-vX.X.X-x86_64.AppImage \
  TuxTalk-vX.X.X-x86_64.AppImage.zsync \
  TalkType-vX.X.X-x86_64.AppImage.zsync \
  tuxtalk_X.X.X_amd64.deb \
  tuxtalk-X.X.X-1.x86_64.rpm \
  tuxtalk-gnome-extension.zip \
  talktype-gnome-extension.zip \
  SHA256SUMS.txt \
  --title "..." --notes "..."
```

Note the .deb and .rpm use the bare version (`0.7.2`), NOT the `v` prefix the
tag and AppImage use.

**NEVER create a GitHub release without the .deb and .rpm.**
They are how every Debian/Ubuntu/Mint and Fedora/RHEL user installs. Omitting
them ships an AppImage-only release and silently strands those users.

**NEVER create a GitHub release without the AppImage's `.zsync` file.**
`./build-release.sh` writes it next to the AppImage. The AppImage carries
update information pointing at the `.zsync` in the *latest* release, so a
release without it breaks AppImageUpdate and similar tools for everyone.

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
Using TuxTalk on Arch? A [vote on the AUR page](https://aur.archlinux.org/packages/tuxtalk-appimage) helps other Arch users find it.
```

AUR votes only move when asked for — the package sat at zero from December
2025 to at least August 2026 while still being installed regularly.

---

## VULKAN GRAPHICS ENGINE — BUILT AND HOSTED SEPARATELY

The "Vulkan (any GPU)" device (config value `vulkan`; AMD, Intel and NVIDIA)
runs whisper.cpp's whisper-server with its Vulkan backend (`src/tuxtalk/whisper_vulkan.py`). whisper.cpp publishes no
Linux Vulkan build, so TuxTalk builds one. It is NOT part of the AppImage
and is NOT rebuilt for each release. It only changes when whisper.cpp does.

To update it:
1. `./build-vulkan-engine.sh 1.9.4` (the whisper.cpp version). It builds in
   Ubuntu 22.04 and writes `talktype-whisper-vulkan-<ver>-x64.tar.gz` + `.sha256`.
2. Upload it to a GitHub release tagged `whisper-vulkan-<ver>`, marked
   **pre-release** (`gh release create ... --prerelease`). A normal release
   would become "latest", and the in-app updater and the AppImage's update
   information would treat it as a TuxTalk version.
3. Put the version and SHA256 into `ENGINE_VERSION` / `ENGINE_SHA256` in
   `whisper_vulkan.py`.
4. Ask Ron before uploading. It is public.

The setup dialogs (download, speed check, Light/Full choice) live in
`vulkan_setup_dialogs.py`, shared by Preferences and the tray's presets.

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
- **Desktop launcher**: "TuxTalk (Dev)" in `~/.local/share/applications/tuxtalk-dev.desktop`
- **Autostart**: Launches the dev version, NOT the AppImage
- **DEV_MODE=1**: Shows BOTH tray icons (GTK tray + GNOME extension)
- **Source code**: `/home/ron/Projects/TalkType/src/tuxtalk/`

### Autostart Configuration:
```
Exec=env DEV_MODE=1 PYTHONPATH=/home/ron/Projects/TalkType/src:/usr/lib64/python3.14/site-packages:/usr/lib/python3.14/site-packages /home/ron/Projects/TalkType/.venv/bin/python -m tuxtalk.tray
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
- The `src/tuxtalk/` directory
- The development desktop launcher
- Ron's config files without explicit permission

---

## GTK TRAY AND GNOME EXTENSION — KEEP IN SYNC

TuxTalk has TWO user interfaces that must stay synchronized:

1. **GTK Tray Icon** (`src/tuxtalk/tray.py`) — For all Linux desktops
2. **GNOME Shell Extension** (`gnome-extension/talktype@ronb1964.github.io/extension.js`) — For GNOME users

**When adding/modifying menu items or features:**
- Add to BOTH the GTK tray menu AND the GNOME extension menu
- Keep menu order identical between both
- If adding a D-Bus method, update:
  1. `src/tuxtalk/dbus_service.py` — Add the D-Bus method
  2. `src/tuxtalk/tray.py` — Add method to `TrayAppInstance` class
  3. `gnome-extension/.../extension.js` — Add to D-Bus interface AND menu

**Menu order (must match in both):**
```
Dictation Service (toggle)
Restart Service
Recent Dictations ▸
Fix a Word...
─────────────────────
Active Model: [model]
Device: [device]
Performance ▸
Text Injection Mode ▸
─────────────────────
Preferences...
Voice Commands...
Your Stats...
Help...
About TuxTalk...
Check for Updates...
─────────────────────
Quit TuxTalk
```

---

## WORKING STYLE

Explain what code does in plain language. Always:
- Provide exact copy/paste commands (include `cd` commands)
- Be direct and honest
- Never assume the reader will debug code themselves

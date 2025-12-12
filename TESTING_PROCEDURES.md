# TalkType Testing Procedures

## CRITICAL: User's Role vs Claude's Role

**USER:** Only runs the AppImage from `~/AppImages/` directory and tests the UI
**CLAUDE:** Must provide a fresh test environment BEFORE user tests

## Claude's Responsibilities Before User Tests

When the user wants to test an AppImage, Claude MUST:

1. **Run `./fresh-start-for-testing.sh`** to provide a clean environment
2. **Verify the cleanup succeeded** by checking the script output
3. **Show the AppImage file size** (user wants to keep it under 1GB)
4. **Provide exact commands** for the user to copy/paste:
   ```
   cd ~/AppImages
   ./TalkType-v0.3.8-x86_64.AppImage
   ```
   (User is a novice - ALWAYS include the `cd` command!)
5. **Wait** for the user to share terminal output

**NEVER** ask the user to run fresh-start-for-testing.sh themselves!

## Prerequisites for Testing

**Before testing the AppImage, ensure ydotool is installed and running:**

```bash
# Check if ydotoold is running
systemctl --user status ydotoold
```

If not installed or not running:

```bash
# Install ydotool (choose your distro)
# Fedora/Nobara:
sudo dnf install ydotool

# Ubuntu/Debian:
sudo apt install ydotool

# Set up systemd service for ydotool daemon
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/ydotoold.service <<'EOF'
[Unit]
Description=ydotool daemon (Wayland keystroke injector)
After=graphical-session.target

[Service]
Environment=XDG_RUNTIME_DIR=%t
ExecStart=/usr/bin/ydotoold --socket-path=%t/.ydotool_socket
Restart=on-failure

[Install]
WantedBy=default.target
EOF

# Enable and start the service
systemctl --user daemon-reload
systemctl --user enable --now ydotoold.service

# Verify it's running
systemctl --user status ydotoold
```

**Note:** The AppImage requires ydotool to be installed system-wide for text injection to work.

## Fresh Test Environment Setup

**Claude runs this automatically - user never runs this script!**

The `fresh-start-for-testing.sh` script ensures a completely clean first-run environment by:
1. Stopping all TalkType processes
2. Removing config file (`~/.config/talktype/config.toml`)
3. Removing first-run flag (`~/.local/share/TalkType/.first_run_done`)
4. Removing CUDA libraries (`~/.local/share/TalkType/cuda`)
5. Removing all model caches (small, medium, large-v3)
6. Copying latest AppImage to `~/AppImages/`
7. Verifying everything is clean with checkmarks

## Why This Matters

- **Must stop app BEFORE clearing flags**: The app recreates `.first_run_done` on shutdown
- **All caches must be cleared**: To see download progress bars for models
- **CUDA libs must be removed**: To test GPU detection and CUDA download flow
- **Config must be removed**: To test default settings

## Testing Checklist

When testing a new build, verify:
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

## Build and Release Process

1. Make code changes
2. Rebuild AppImage: `./build-appimage-cpu.sh`
3. Set up fresh environment: `./fresh-test-env.sh`
4. Test thoroughly with checklist above
5. If issues found, fix and repeat from step 2
6. When ready to release:
   ```bash
   git add <changed files>
   git commit -m "..."
   git push
   gh release create v0.x.x TalkType-v0.x.x-x86_64.AppImage TalkType-v0.x.x-x86_64.AppImage.zsync --title "..." --notes "..."
   ```

## Important Notes

- **Never** remove first-run flag while app is running
- **Never** skip the fresh environment setup when testing
- **Always** verify the checklist items work before releasing
- The script shows verification output - check that all items show "✓ Removed"

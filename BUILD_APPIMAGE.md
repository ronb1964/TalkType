# Safe AppImage Build Process

## ⚠️ Important: Protecting Your Running Application

**NEVER build AppImages on your main branch or while TalkType is running!**

The AppImage build process copies your entire Python environment and can interfere with your currently running application.

## Safe Build Procedure

### 1. Preparation (Before Building)
```bash
# 1. Stop TalkType completely
systemctl --user stop ron-dictation.service
pkill -f "dictate-tray"
pkill -f "ron_dictation"

# 2. Switch to build branch
git checkout appimage-builds

# 3. Ensure clean state
git status  # Should show no uncommitted changes
```

### 2. Build the AppImage
```bash
# Build in isolated environment
./appimage-builder --recipe appimage-builder.yml

# The build creates:
# - TalkType-x86_64.AppImage (your distributable)
# - AppDir/ gets populated with full Python environment
```

### 3. Test the AppImage (Optional)
```bash
# Test the generated AppImage
./TalkType-x86_64.AppImage --help
./TalkType-x86_64.AppImage tray &  # Test tray
./TalkType-x86_64.AppImage prefs   # Test preferences
```

### 4. Return to Working State
```bash
# 1. Switch back to main branch
git checkout main

# 2. Clean up build artifacts (they're gitignored anyway)
rm -rf AppDir/usr/  # Remove copied Python environment
git clean -fd      # Remove any other build artifacts

# 3. Restart your development environment
systemctl --user start ron-dictation.service
# Or manually start tray: dictate-tray &
```

## Why This Process Works

1. **Branch Isolation**: Build artifacts stay on the build branch
2. **Service Stopping**: Prevents conflicts with running processes
3. **Clean Separation**: Your main development environment remains untouched
4. **Easy Recovery**: Switch back to main branch restores everything

## Build Branch Maintenance

The `appimage-builds` branch should:
- Be kept in sync with main for source code
- Only differ in build artifacts and build-specific configs
- Never be used for development work

```bash
# Sync build branch with latest main
git checkout appimage-builds
git rebase main  # Brings in latest changes
```

## Alternative: Docker Build (Future)

For even better isolation, consider using Docker:
```bash
# Future improvement - build in container
docker run --rm -v $(pwd):/workspace appimage-builder
```

## Troubleshooting

**If your app breaks after building:**
1. Stop all TalkType processes
2. Switch to main branch: `git checkout main`
3. Clean workspace: `git clean -fd`
4. Restart Poetry environment: `poetry install`
5. Restart services: `systemctl --user restart ron-dictation.service`


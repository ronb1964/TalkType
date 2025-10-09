# AppImageHub Submission Guide for TalkType

## Prerequisites Checklist

Before submitting to AppImageHub, ensure you have:

- [x] Valid AppStream metadata (`io.github.ronb1964.TalkType.appdata.xml`)
- [x] Working AppImage (`TalkType-v0.3.6-x86_64.AppImage`)
- [x] GitHub repository (https://github.com/ronb1964/TalkType)
- [ ] Screenshots in AppStream metadata
- [ ] GitHub Release with AppImage uploaded
- [ ] AppImage accessible via direct wget URL

## Current Status

✅ AppStream metadata is valid (warnings about URLs are OK - they'll work once the repo is public)
✅ AppImage built and ready: `TalkType-v0.3.6-x86_64.AppImage` (2.7GB)
✅ GitHub repository exists: `ronb1964/TalkType`

## Step-by-Step Submission Process

### Step 1: Add Screenshots to AppStream Metadata (OPTIONAL but RECOMMENDED)

Screenshots help users see your app before downloading. Add to `io.github.ronb1964.TalkType.appdata.xml`:

```xml
<screenshots>
  <screenshot type="default">
    <caption>TalkType system tray and preferences</caption>
    <image>https://raw.githubusercontent.com/ronb1964/TalkType/main/screenshots/main.png</image>
  </screenshot>
  <screenshot>
    <caption>Dictation in action</caption>
    <image>https://raw.githubusercontent.com/ronb1964/TalkType/main/screenshots/dictating.png</image>
  </screenshot>
</screenshots>
```

Add this section before `<releases>` tag.

To create screenshots:
1. Create `screenshots/` directory in your repo
2. Take screenshots of your app (PNG format, 1280x720 or similar)
3. Commit and push to GitHub
4. Update the AppStream XML with the correct URLs

### Step 2: Create GitHub Release with AppImage

You need to create a GitHub release and upload your AppImage:

```bash
# Make sure you're in the project directory
cd /home/ron/projects/TalkType

# Create a release and upload the AppImage
gh release create v0.3.6 \
  --title "v0.3.6 - Polished First-Run Experience" \
  --notes "See CHANGELOG or AppStream metadata for details" \
  TalkType-v0.3.6-x86_64.AppImage
```

This will:
- Create a new release tagged `v0.3.6`
- Upload your AppImage to the release
- Make it available at a permanent URL like:
  `https://github.com/ronb1964/TalkType/releases/download/v0.3.6/TalkType-v0.3.6-x86_64.AppImage`

### Step 3: Test the Download URL

Verify your AppImage is downloadable:

```bash
wget https://github.com/ronb1964/TalkType/releases/download/v0.3.6/TalkType-v0.3.6-x86_64.AppImage
```

### Step 4: Submit to AppImageHub

1. Go to: https://github.com/AppImage/AppImageHub/new/master/data

2. Create a new file named: `TalkType`

3. In the file content, put ONLY this line:
   ```
   https://github.com/ronb1964/TalkType
   ```

4. Scroll down and create a pull request with:
   - Title: `Add TalkType`
   - Description:
     ```
     TalkType - AI-powered speech recognition and dictation for Wayland

     - Privacy-focused offline dictation using Faster-Whisper
     - Press-and-hold hotkey interface
     - Smart punctuation and voice commands
     - System tray integration
     - GPU acceleration support
     ```

5. Submit the PR

### Step 5: Wait for Automated Review

AppImageHub will automatically:
- Download your AppImage from the GitHub release
- Run validation tests
- Check AppStream metadata
- Verify desktop file
- Test if it runs

You'll see the results in the PR:
- ✅ Green checkmark = Success! Your app will be added to AppImageHub
- ❌ Red X = Issues found, check the build log and fix

## Important Notes

### File Naming Convention
Your AppImage follows the correct naming:
- `TalkType-v0.3.6-x86_64.AppImage` ✅
- Format: `AppName-Version-Architecture.AppImage`

### AppStream Requirements
- [x] Valid `id`: `io.github.ronb1964.TalkType`
- [x] Valid `metadata_license`: `CC0-1.0`
- [x] Valid `project_license`: `MIT`
- [x] Has `name`, `summary`, `description`
- [x] Has categories
- [x] Has releases section
- [ ] Has screenshots (optional but recommended)

### GitHub Release Requirements
- Must be tagged (e.g., `v0.3.6`)
- AppImage must be uploaded as a release asset
- Must be publicly accessible (not draft)
- URL must be stable and permanent

### AppImage Requirements (Already Met)
- [x] Contains desktop file
- [x] Contains icon
- [x] Contains AppStream metadata
- [x] Executable
- [x] Follows naming convention

## Common Issues and Solutions

**Issue**: "URL not reachable"
- **Solution**: Ensure GitHub release is public and AppImage is uploaded

**Issue**: "AppStream validation failed"
- **Solution**: Run `appstreamcli validate io.github.ronb1964.TalkType.appdata.xml`

**Issue**: "Desktop file invalid"
- **Solution**: Check `io.github.ronb1964.TalkType.desktop` syntax

**Issue**: "AppImage too large"
- **Note**: Your 2.7GB AppImage is large. This is OK but consider:
  - Excluding unnecessary dependencies
  - Stripping debug symbols
  - Your CPU-only build script already optimizes this

## After Submission

Once approved:
- Your app appears on https://www.appimagehub.com
- Users can search and download it
- AppImage will appear in AppImage catalogs/stores
- Updates require a new PR (not automatic)

## Future Updates

When you release a new version:
1. Build new AppImage with new version number
2. Create new GitHub release with new tag
3. Upload new AppImage to release
4. AppImageHub will automatically detect and update (if using GitHub repo URL)

OR

Submit a new PR to update the data file if needed.

## Quick Reference Commands

```bash
# Create release and upload AppImage
gh release create v0.3.6 \
  --title "v0.3.6 - Polished First-Run Experience" \
  --notes "Improved first-run UX with streamlined hotkey setup and model download progress" \
  TalkType-v0.3.6-x86_64.AppImage

# Test download
wget https://github.com/ronb1964/TalkType/releases/download/v0.3.6/TalkType-v0.3.6-x86_64.AppImage

# Validate AppStream
appstreamcli validate io.github.ronb1964.TalkType.appdata.xml
```

## Support

- AppImageHub issues: https://github.com/AppImage/AppImageHub/issues
- AppImage documentation: https://docs.appimage.org/
- AppImage forum: https://discourse.appimage.org/

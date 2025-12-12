# GNOME Extension Fixes Needed

**Session Date:** 2025-10-15 11:00 PM

## Issues Found

### 1. Icon Display Issue (FIXED in icon appearance, but code needs update)
- **Location:** `/home/ron/.local/share/gnome-shell/extensions/talktype@ronb1964.github.io/extension.js:75-86`
- **Problem:** Extension tries to load local `icon.svg` file that doesn't exist, causing white dot icon initially
- **Fix:** Lines 75-86 should use symbolic icon directly instead of trying to load local file:
  ```javascript
  // Remove the FileIcon approach (lines 79-80)
  // Use this instead:
  this._icon = new St.Icon({
      icon_name: 'audio-input-microphone-symbolic',
      style_class: 'system-status-icon',
  });
  ```
- **Also fix:** Line 211 tries to set `icon_name` on a FileIcon which doesn't work properly

### 2. Model Name Display Shows "[object variant of type "s"]"
- **Location:** `/home/ron/.local/share/gnome-shell/extensions/talktype@ronb1964.github.io/extension.js:201`
- **Problem:** The status.model is a GVariant that needs to be unpacked to get the actual string value
- **Screenshot:** Shows `Model: [object variant of type "s"]` instead of actual model name
- **Fix:** Need to unpack the GVariant properly:
  ```javascript
  // Line 201 - need to deep_unpack() the variant
  this._currentModel = status.model.deep_unpack() || 'unknown';
  ```

### 3. Help Button Does Nothing
- **Location:** `/home/ron/.local/share/gnome-shell/extensions/talktype@ronb1964.github.io/extension.js:166-170`
- **Problem:** Help button has empty callback (line 168 is just a comment)
- **Fix:** Should call OpenPreferences D-Bus method (same as Preferences button):
  ```javascript
  helpItem.connect('activate', () => {
      this._proxy.OpenPreferencesRemote();
  });
  ```

### 4. Quit Button May Not Work
- **Location:** `/home/ron/.local/share/gnome-shell/extensions/talktype@ronb1964.github.io/extension.js:176-178`
- **Problem:** Calls `this._proxy.QuitRemote()` but needs verification that D-Bus Quit method works
- **D-Bus Method:** `src/talktype/dbus_service.py:141-145` - looks correct
- **Fix:** Need to test if the app.quit() method exists and works properly

### 5. Recording Animation Satellites Get Cut Off
- **Location:** Recording indicator animation (large size)
- **Problem:** When using large recording indicator size, the satellite circles get cut off at their maximum travel distance
- **Fix:** Need to increase the bounding box/container size for the animation to accommodate full satellite orbit radius
- **Files to check:**
  - `src/talktype/prefs.py` - where size is configured
  - Animation rendering code - wherever the recording indicator is drawn

## Testing Verification Needed

After fixes:
1. ✅ Icon appears correctly from start (no white dot)
2. ✅ Model name displays as "Large-v3" not "[object variant...]"
3. ✅ Help button opens preferences
4. ✅ Quit button properly quits TalkType application
5. ✅ Large recording indicator satellites don't get clipped

## Files to Update

1. `/home/ron/.local/share/gnome-shell/extensions/talktype@ronb1964.github.io/extension.js`
2. `/home/ron/projects/TalkType/gnome-extension/talktype@ronb1964.github.io/extension.js` (source)
3. Recording indicator animation code (find the file that renders it)
4. After fixing, need to rebuild the zip and reinstall extension

## Future Enhancement: Custom Icon

### 6. Create Custom Symbolic Icon for TalkType
- **Goal:** Design a unique monochrome/symbolic icon for TalkType that works across all desktop environments
- **Style Requirements:**
  - Monochrome (single color - white/black)
  - Symbolic SVG format for proper theme integration
  - Clean, simple lines (works at 16x16 to 24x24 pixels)
  - Should be recognizable as TalkType (not generic microphone)
- **Ideas:**
  - Microphone with small "T" badge
  - Stylized mic with sound waves
  - Microphone inside speech bubble
  - Mic with keyboard/typing indicator
- **Files to Create:**
  - `talktype-symbolic.svg` - main symbolic icon
  - Bundle with GNOME extension: `gnome-extension/talktype@ronb1964.github.io/icon.svg`
  - Update GTK tray to use custom icon in `src/talktype/tray.py`
- **Benefits:**
  - Unique branding across all DEs (GNOME/KDE/etc.)
  - Professional appearance
  - Better visual identity for TalkType

## Notes

- The icon eventually shows correctly (as seen in screenshot 22-48-04), but the code is still wrong
- All GVariant values from D-Bus need proper unpacking with `.deep_unpack()`
- Need to find where recording indicator is rendered to fix satellite clipping issue
- Custom icon should follow freedesktop.org symbolic icon guidelines

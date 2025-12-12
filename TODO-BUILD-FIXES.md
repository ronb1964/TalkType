# Build Issues to Fix

## Status
- Extension auto-enable fix: ✅ DONE (in source code)
- Build script consolidation: ✅ DONE (build-release.sh)
- Working AppImage: ❌ NEEDS FIXES

## Remaining Issues

### 1. AppImage Size (1.1GB instead of 887MB)
**Problem:** New build includes unnecessary packages
**Packages to exclude:**
- cusparselt (203MB)
- sympy (28MB)
- networkx (7.3MB)
- torchvision (11MB)
- torchaudio (9.4MB)

**Fix:** Already added exclusions to `build-release.sh:118-138`
**Status:** Ready to rebuild

### 2. Missing AppIndicator3 Typelib
**Problem:** AppImage crashes with `ValueError: Namespace AppIndicator3 not available`
**Fix:** Already added `apt-get install gir1.2-appindicator3-0.1` to `build-release.sh:188`
**Status:** Ready to rebuild

## Next Steps
1. Run `./build-release.sh` - will take ~5 minutes
2. Test the AppImage launches without errors
3. Test extension installation and auto-enable
4. Log out/in to verify extension loads automatically

## Code Changes Made
- `src/talktype/extension_helper.py:152` - Added `enable_extension()` call after installation
- `build-release.sh` - Complete new build script (Ubuntu 22.04 container, Python 3.10)
- Old build scripts moved to `old-build-scripts/`

## Testing Checklist
- [ ] AppImage size is ~900MB
- [ ] AppImage launches successfully
- [ ] Extension installs without errors
- [ ] Extension auto-enables (check with `gnome-extensions info talktype@ronb1964.github.io`)
- [ ] After logout/login, extension appears in top panel

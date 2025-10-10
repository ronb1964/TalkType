# Next Session - TalkType Development

## ⚠️ MANDATORY: Read This FIRST!

### Testing Procedure (ALWAYS USE THIS!)

**Before testing ANY AppImage build, run:**
```bash
./fresh-test-env.sh
```

This script ensures a completely fresh first-run environment:
- Stops all TalkType processes
- Removes config file
- Removes first-run flag
- Removes CUDA libraries
- Removes all model caches (small, medium, large)
- Copies latest AppImage to ~/AppImages/
- Shows verification checkmarks

**CRITICAL:** Never remove first-run flag while app is running - it will be recreated on shutdown!

See `TESTING_PROCEDURES.md` for full testing checklist and procedures.

---

## 🎯 Current Status (as of 2025-10-10)

### 🚧 Working On v0.3.7
- **Status:** Fixing bugs found in testing
- **Current Issues:**
  - CUDA download green checkmark doesn't appear immediately (only after OK clicked)
  - Need to test auto-switch to GPU after CUDA download

### ✅ Recently Fixed
- `self.s.device` → `self.config.get("device")` bug in prefs.py
- `self.save_settings()` → `self.save_config()` bug in prefs.py
- Bundled ydotool for AppImageHub compatibility
- Fixed nvidia package exclusion (was including 2.7GB of nvidia packages)
- Set proper defaults: auto_period=True, auto_timeout=5min, language_mode=auto
- Improved auto-period UI with better label and tooltip

### 📦 AppImage Status
- **Size:** 890MB
- **Version:** v0.3.7 (in testing, not yet released)
- **Last Release:** v0.3.7 (draft - needs more testing)
- **AppImageHub PR:** https://github.com/AppImage/appimage.github.io/pull/3511
  - Status: Waiting for v0.3.7 testing to complete before re-running checks

### 🔄 Backups Created
- CUDA libraries: `~/.local/share/TalkType/cuda.backup.*`
- Config: `~/.config/talktype.backup.20251009_193702`
- To restore: See commands in `CROSS_PLATFORM_PORTING_GUIDE.md`

---

## 🚀 What to Work On Next

### Option 1: Start v0.4.0 Development
**Implement Phase 1 features from `ROADMAP_v0.4.0.md`:**

1. **Quick Model Switcher** (tray menu)
   - Add model selection submenu to system tray
   - Update config on selection
   - Reload model if service running

2. **Custom Voice Commands**
   - User-definable phrase replacements
   - "my email" → actual email address
   - Store in config file

3. **Undo Last Dictation**
   - Hotkey (Ctrl+Shift+Z or F7)
   - Delete last transcribed text

4. **Auto-capitalize After New Line**
   - Capitalize first letter after new line/paragraph

5. **Fix GTK Deprecation Warning**
   - Replace `dialog.get_action_area()` calls

**To start:** Say "Let's work on v0.4.0" or pick a specific feature

---

### Option 2: Check AppImageHub Status
**Command to check PR status:**
```bash
gh pr view 3511 --repo AppImage/appimage.github.io
```

**If approved:**
- Celebrate! 🎉
- Check TalkType on https://www.appimagehub.com

**If needs changes:**
- Review feedback and address issues

---

### Option 3: Cross-Platform Exploration
**If interested in macOS/Windows support:**
- Review `CROSS_PLATFORM_PORTING_GUIDE.md`
- Build proof-of-concept with cross-platform libraries
- See "Recommended Approach" section in guide

---

### Option 4: Other Improvements
- Performance optimization
- Documentation updates
- Bug fixes from user feedback
- New feature ideas

---

## 📚 Key Documentation Files

1. **`ROADMAP_v0.4.0.md`** - Feature roadmap and priorities
2. **`CROSS_PLATFORM_PORTING_GUIDE.md`** - macOS/Windows porting guide
3. **`APPIMAGEHUB_SUBMISSION.md`** - AppImageHub submission checklist
4. **`ICON_DOCUMENTATION.md`** - Icon management guide
5. **`README.md`** - User documentation (with screenshots)

---

## 🔧 Current Configuration

**AppImage Build:**
- Script: `build-appimage-cpu.sh`
- Size optimizations: Strips unnecessary files
- CUDA: Full GPU support included
- Icon: Protected retro square light design

**Git Status:**
- Branch: main
- Latest commit: Screenshots and documentation
- Clean working directory

---

## 💡 Quick Commands for Next Session

### Check AppImageHub PR
```bash
gh pr view 3511 --repo AppImage/appimage.github.io
gh pr checks 3511 --repo AppImage/appimage.github.io
```

### Build New AppImage
```bash
./build-appimage-cpu.sh
```

### Test AppImage (First-Run)
```bash
rm ~/.local/share/TalkType/.first_run_done
mv ~/.local/share/TalkType/cuda ~/.local/share/TalkType/cuda.backup
./TalkType-v0.3.6-x86_64.AppImage
```

### Restore After Testing
```bash
mv ~/.local/share/TalkType/cuda.backup.* ~/.local/share/TalkType/cuda
touch ~/.local/share/TalkType/first_run_complete
```

### Start Development
```bash
poetry run dictate-tray  # Run dev version
poetry run pytest -q     # Run tests
```

---

## 🎯 Recommended Next Steps

**My suggestion for next session:**

1. **Quick Check:** See if AppImageHub approved the submission
2. **Start v0.4.0:** Implement Quick Model Switcher (easiest, high impact)
3. **Add Tests:** Write tests for new features as we add them
4. **Update Docs:** Keep README and ROADMAP updated

**Most impactful features to start with:**
- ✅ Quick Model Switcher (tray menu) - Users will love this!
- ✅ Custom Voice Commands - Huge productivity boost
- ✅ Auto-capitalize after new line - Better UX

---

## 📝 Notes & Reminders

- AppImage size budget: Keep under 1GB (currently 870MB)
- All new features should work without bloating size
- Test first-run experience after each feature
- Update AppStream metadata for new releases
- Keep icon documentation updated (don't change the icon!)

---

## 🤔 Open Questions / Ideas

- Should we add multi-language support in v0.4.0?
- Would users want dictation macros/scripts?
- Should we create a Discord/forum for users?
- Consider adding telemetry (opt-in) to understand usage?

### ⚡ Quick Fix Needed: "dot" Command Behavior

**Current behavior:**
- Saying "dot" → `. ` (period + space + capitalize next letter)
- Example: "my email is ron dot com" → "my email is ron. Com" ❌

**Desired behavior:**
- Context-aware "dot" command:
  - **In text/sentences:** "dot" → `. ` (period + space + capitalize) - current behavior
  - **In URLs/emails:** "dot" → `.` (just period, no space/capitalize)

**Solution Options:**

1. **Add new command:** "literal dot" or "no space dot" → `.` (no space)
   - Keeps current "dot" behavior unchanged
   - Users can choose which to use

2. **Smart detection:** Detect if in URL/email context
   - Look for words before: "www", "http", "com", "org", email patterns
   - Auto-use literal dot in those contexts

3. **Add "dot com" as special phrase** → `.com`
   - Also: "dot org", "dot net", "dot edu", etc.
   - Quick fix for common use case

**Recommended approach:** Option 3 (quick) + Option 1 (comprehensive)
- Add common TLD phrases: "dot com", "dot org", "dot net" → `.com`, `.org`, `.net`
- Add "literal dot" command → `.` (no space/capitalize)
- Keep regular "dot" unchanged for sentences

**Implementation:**
- File: `src/talktype/normalize.py`
- Add to voice command replacements
- Test with: "email me at john dot smith at gmail dot com"

---

**Last Updated:** 2025-10-09
**Next Release Target:** v0.4.0 (aiming for 1-2 weeks)

---

## To Resume Next Session:

Just say:
- "What should we work on?" (I'll read this file and suggest)
- "Let's implement [feature name]"
- "Check AppImageHub status"
- "Review the roadmap"

All your work is documented and ready to continue! 🚀

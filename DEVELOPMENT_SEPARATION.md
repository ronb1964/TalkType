# Development Separation Guide

## 🛡️ Keeping Installed App and AppImage Development Separate

### **Branch Strategy**

#### **`main` branch - INSTALLED APP ONLY**
- ✅ **Purpose:** Production code for installed Poetry version
- ✅ **Testing:** Use `poetry run` commands
- ✅ **Changes:** Only core application features
- ❌ **Never:** AppImage build files or AppDir modifications

#### **`appimage-builds` branch - APPIMAGE DEVELOPMENT**
- ✅ **Purpose:** AppImage packaging and distribution
- ✅ **Testing:** AppImage builds and testing
- ✅ **Changes:** Build scripts, AppDir, packaging fixes
- ❌ **Never:** Core application logic changes

### **🔒 Safe Development Workflow**

#### **For Installed App Development:**
```bash
# Always work on main branch
git checkout main

# Test with installed version
poetry run dictate-tray
poetry run dictate-prefs

# Make changes to core app
edit src/ron_dictation/*.py

# Test changes
poetry run pytest
```

#### **For AppImage Development:**
```bash
# Switch to AppImage branch
git checkout appimage-builds

# Sync latest app code from main
git merge main

# Work on packaging only
edit build-appimage-*.sh
edit AppDir/AppRun

# Build and test AppImage
./build-appimage-clean.sh
```

### **🚨 Critical Rules**

1. **Never modify core app code on `appimage-builds` branch**
2. **Never build AppImages on `main` branch**
3. **Always stop installed services before AppImage testing**
4. **Always switch back to main for daily use**

### **📁 File Ownership by Branch**

#### **`main` branch owns:**
- `src/ron_dictation/*.py` (core application)
- `pyproject.toml` (dependencies)
- `tests/` (unit tests)
- `README.md` (user documentation)

#### **`appimage-builds` branch owns:**
- `build-appimage-*.sh` (build scripts)
- `AppDir/` (packaging directory)
- `BUILD_APPIMAGE.md` (build documentation)
- `appimage-builder.yml` (build config)

### **⚡ Quick Commands**

#### **Switch to Daily Use (Installed App):**
```bash
git checkout main
systemctl --user start ron-dictation.service
```

#### **Switch to AppImage Development:**
```bash
git checkout appimage-builds
systemctl --user stop ron-dictation.service
./build-appimage-clean.sh
```

#### **Emergency Reset if Confused:**
```bash
# Stop everything
pkill -f "dictate\|TalkType\|ron_dictation"
systemctl --user stop ron-dictation.service

# Go back to stable main
git checkout main
git reset --hard origin/main

# Restart installed version
systemctl --user start ron-dictation.service
```

### **🎯 Benefits**

- ✅ **No cross-contamination** between versions
- ✅ **Clear separation** of concerns
- ✅ **Safe experimentation** with AppImage builds
- ✅ **Stable daily use** with installed version
- ✅ **Easy recovery** if something breaks

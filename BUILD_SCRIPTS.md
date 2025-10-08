# Build Scripts Documentation

This project includes multiple AppImage build scripts for different use cases. **Use `build-appimage-cpu.sh` for production builds.**

## 📋 Build Scripts Overview

### ✅ **build-appimage-cpu.sh** (Recommended - 13KB)
**Purpose**: Production CPU-only AppImage build

**Features**:
- Creates optimized CPU-only AppImage (~250MB vs ~1.5GB with CUDA)
- GPU/CUDA libraries downloaded at runtime if needed (~1.2GB)
- Smart GPU detection on first run
- Automatic Python version detection (3.10-3.13)
- Clean build with proper dependency handling

**When to use**:
- Distribution to end users
- CI/CD pipelines
- Release builds

**Build time**: ~5-10 minutes (includes fresh venv creation)

**Usage**:
```bash
./build-appimage-cpu.sh
```

**Output**: `TalkType-CPU-x86_64.AppImage` in project root

---

### 🧹 **build-appimage-clean.sh** (4.6KB)
**Purpose**: Clean build from scratch

**Features**:
- Removes all build artifacts (AppDir/, *.AppImage)
- Calls build-appimage-cpu.sh for fresh build
- Useful for troubleshooting build issues

**When to use**:
- Build issues or corruption
- Testing clean builds
- After major dependency changes

**Usage**:
```bash
./build-appimage-clean.sh
```

---

### ⚡ **build-appimage-fast.sh** (2.3KB)
**Purpose**: Quick rebuilds during development

**Features**:
- Reuses existing AppDir/ (no clean)
- Skips dependency reinstallation
- Fast iteration for code-only changes

**When to use**:
- Iterative development
- Testing code changes
- Debugging

**⚠️ Warning**: May not reflect dependency changes. Use clean build for releases.

**Usage**:
```bash
./build-appimage-fast.sh
```

**Build time**: ~30 seconds

---

### 🔧 **build-appimage-manual.sh** (5.5KB)
**Purpose**: Manual/experimental builds

**Features**:
- Custom build configurations
- Testing experimental features
- Advanced debugging

**When to use**:
- Development experimentation
- Custom configurations
- Advanced debugging scenarios

**Usage**:
```bash
./build-appimage-manual.sh
```

---

## 🎯 Quick Decision Guide

| **Scenario** | **Use This Script** |
|-------------|-------------------|
| **Release build** | `build-appimage-cpu.sh` |
| **Clean rebuild** | `build-appimage-clean.sh` |
| **Quick iteration** | `build-appimage-fast.sh` |
| **Development/testing** | `build-appimage-manual.sh` |
| **Build failing** | `build-appimage-clean.sh` |
| **Dependency updated** | `build-appimage-clean.sh` |
| **Code-only change** | `build-appimage-fast.sh` |

---

## 🏗️ Build Process (build-appimage-cpu.sh)

1. **Detect Python version** (3.10-3.13 supported)
2. **Create fresh virtual environment** in AppDir/
3. **Install dependencies** via Poetry
4. **Copy source files** to AppDir/usr/src/
5. **Create launcher scripts** (dictate, dictate-tray)
6. **Copy desktop entry and icons**
7. **Package AppImage** using appimage-builder

---

## 📦 Output Files

All scripts produce AppImage files in the project root:

- `TalkType-CPU-x86_64.AppImage` - CPU-only build (recommended)
- `TalkType-CUDA-x86_64.AppImage` - Pre-bundled CUDA build (deprecated)

**AppDir/**: Intermediate build directory (can be removed after build)

---

## 🐛 Troubleshooting

### Build fails with dependency errors
```bash
./build-appimage-clean.sh  # Start fresh
```

### AppImage doesn't run
```bash
chmod +x TalkType-CPU-x86_64.AppImage
./TalkType-CPU-x86_64.AppImage --help
```

### Python version issues
```bash
# Check detected version
./build-appimage-cpu.sh | grep "Python version"
```

### CUDA runtime issues
- CPU build handles this automatically
- CUDA libraries download on first run if GPU detected
- Manual download: Right-click tray → "Download CUDA Libraries"

---

## 🔄 Migration from Old Builds

If you previously used CUDA-bundled AppImages:

1. **Switch to CPU build**: Use `build-appimage-cpu.sh`
2. **Size benefit**: ~250MB vs ~1.5GB
3. **Same functionality**: CUDA downloads automatically when needed
4. **First run**: May see CUDA download prompt (one-time, 1.2GB)

---

## 📝 Notes

- **Python compatibility**: Auto-detects Python 3.10-3.13
- **Portable**: AppImages run on most Linux distros
- **No sudo required**: Builds in user space
- **Logs**: Build output shows progress and any errors
- **Cleanup**: `rm -rf AppDir/ *.AppImage` to remove build artifacts

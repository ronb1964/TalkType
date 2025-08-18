# TalkType Repository Structure & Build Workflow

## 📁 Repository Layout

TalkType uses a **two-repository structure** to maintain clean separation between development and distribution:

### Development Repository: `/home/ron/projects/TalkType/`
- **Purpose**: Source code development, testing, version control
- **Contains**: 
  - Source code (`src/talktype/`)
  - Tests (`tests/`)
  - Development documentation
  - Build scripts and configuration
  - Poetry environment
- **Activities**: 
  - Code development and testing
  - Git commits and pushes
  - Documentation updates
  - Feature development

### Distribution Repository: `/home/ron/projects/TalkType-Releases/`
- **Purpose**: AppImage building and release distribution
- **Contains**:
  - Built AppImage files
  - Release documentation
  - Distribution-specific files
- **Activities**:
  - AppImage building
  - Release packaging
  - Distribution to users

## 🔄 Build Workflow

### ⚠️ CRITICAL: Always Build in TalkType-Releases

**NEVER build AppImages in the development repository!**

### Correct Build Process:

1. **Develop in TalkType/**
   ```bash
   cd /home/ron/projects/TalkType/
   # Make changes, test, commit
   git add . && git commit -m "Your changes"
   git push
   ```

2. **Prepare TalkType-Releases/ for building**
   ```bash
   cd /home/ron/projects/TalkType-Releases/
   
   # Copy source code
   cp -r ../TalkType/src/ .
   cp -r ../TalkType/tests/ .
   
   # Copy build configuration
   cp ../TalkType/appimage-builder.yml .
   cp ../TalkType/build-appimage-*.sh .
   cp -r ../TalkType/scripts/ .
   cp ../TalkType/pyproject.toml .
   cp ../TalkType/poetry.lock .
   
   # Copy AppDir if it exists
   cp -r ../TalkType/AppDir/ . 2>/dev/null || true
   ```

3. **Build AppImage in TalkType-Releases/**
   ```bash
   cd /home/ron/projects/TalkType-Releases/
   ./scripts/safe-appimage-build.sh
   # or
   ./build-appimage-clean.sh
   ```

4. **Commit and distribute**
   ```bash
   cd /home/ron/projects/TalkType-Releases/
   git add TalkType-*.AppImage
   git commit -m "Release v1.x.x - AppImage build"
   git push
   ```

## 🎯 Benefits of This Structure

- **Clean Development**: Main repo stays focused on source code
- **Isolated Builds**: AppImage builds don't interfere with development environment
- **Separate Concerns**: Development vs distribution are cleanly separated
- **Safe Building**: No risk of corrupting development environment
- **Easy Distribution**: Users can download from TalkType-Releases without development clutter

## 📝 Quick Reference Commands

```bash
# Development work
cd /home/ron/projects/TalkType/

# AppImage building
cd /home/ron/projects/TalkType-Releases/

# Copy for build (run from TalkType-Releases/)
rsync -av --exclude='.git' --exclude='__pycache__' --exclude='.venv' \
    ../TalkType/ ./
```

## 🚨 Remember

- Development = `/home/ron/projects/TalkType/`
- Building = `/home/ron/projects/TalkType-Releases/`
- Always copy source before building
- Never build in the development repository

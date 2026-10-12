# TuxTalk Cross-Desktop Environment Testing

This directory contains the infrastructure for testing TuxTalk across different Linux desktop environments (GNOME, KDE, XFCE) using containerization.

## 🎯 Purpose

Testing GTK applications across different desktop environments can be challenging. This suite provides:

1. **Visual Verification** - Screenshots of TuxTalk UI in different DEs
2. **Automated Testing** - Run pytest tests in each environment
3. **Easy Comparison** - HTML report with side-by-side screenshots
4. **Fast Iteration** - Containerized environments that start in seconds

## 🚀 Quick Start

### One Command to Test Everything

```bash
cd /home/ron/Dropbox/projects/TuxTalk
./test-all-de.sh
```

This will:
1. Build container images for GNOME, KDE, and XFCE
2. Take screenshots of TuxTalk in each environment
3. Generate an HTML comparison report
4. Open the report in your browser

### After Initial Build

Skip rebuilding containers on subsequent runs:

```bash
./test-all-de.sh --no-build
```

## 📁 File Structure

```
docker-testing/
├── Dockerfile.gnome        # GNOME environment container
├── Dockerfile.kde          # KDE Plasma environment container
├── Dockerfile.xfce         # XFCE environment container
├── test-runner.sh          # Runs inside containers
├── build-all.sh            # Builds all container images
├── run-tests.sh            # Runs tests across all environments
├── generate-comparison-report.sh  # Creates HTML report
└── README.md               # This file

../test-screenshots/        # Generated screenshots
../test-all-de.sh          # Main entry point
```

## 🔧 Manual Usage

### Build Containers

```bash
cd docker-testing
./build-all.sh
```

This creates three Podman images:
- `tuxtalk-test:gnome`
- `tuxtalk-test:kde`
- `tuxtalk-test:xfce`

### Take Screenshots

```bash
cd docker-testing
./run-tests.sh screenshot
```

Screenshots saved to: `../test-screenshots/`

### Run Automated Tests

```bash
cd docker-testing
./run-tests.sh test
```

### Generate Comparison Report

```bash
cd docker-testing
./generate-comparison-report.sh
```

Opens: `../test-screenshots/comparison-report.html`

## 🖥️ What Gets Tested

Each container:
- Runs a virtual X server (Xvfb)
- Loads the appropriate desktop environment theme
- Launches TuxTalk preferences window
- Takes a screenshot
- Saves to shared volume

The comparison report shows all screenshots side-by-side for easy visual comparison.

## 🛠️ How It Works

### Container Architecture

Each Dockerfile sets up:
1. **Base OS:** Fedora Linux (lightweight)
2. **Desktop Environment:** GNOME/KDE/XFCE themes and GTK libraries
3. **Dependencies:** Python, PyGObject, GTK3/GTK4
4. **Virtual Display:** Xvfb for headless operation
5. **Screenshot Tools:** gnome-screenshot, spectacle, or xfce4-screenshooter

### Test Flow

```
┌─────────────────┐
│  test-all-de.sh │ Main entry point
└────────┬────────┘
         │
    ┌────▼─────┐
    │  Build   │ Podman builds containers
    │ (once)   │
    └────┬─────┘
         │
    ┌────▼──────────┐
    │  Run Tests    │ Launches containers
    │  (3 parallel) │ one per DE
    └────┬──────────┘
         │
    ┌────▼──────────┐
    │ test-runner   │ Inside each container:
    │   (in each    │ 1. Start Xvfb
    │  container)   │ 2. Launch TuxTalk
    └────┬──────────┘ 3. Take screenshot
         │
    ┌────▼──────────┐
    │  Screenshots  │ Saved to shared volume
    │  (on host)    │ test-screenshots/
    └────┬──────────┘
         │
    ┌────▼──────────┐
    │ Generate      │ Creates HTML with
    │  Report       │ side-by-side images
    └────┬──────────┘
         │
    ┌────▼──────────┐
    │  Open in      │ View results!
    │  Browser      │
    └───────────────┘
```

## 📸 Screenshot Modes

### 1. Preferences Window (Default)

Captures the TuxTalk preferences dialog in each DE.

### 2. Custom Windows

Edit `test-runner.sh` to launch different windows:

```bash
# Launch main tray icon
python3 -m tuxtalk.tray &

# Or launch specific dialog
python3 -m tuxtalk.welcome_dialog &
```

## 🧪 Running Pytest Tests

Instead of screenshots, run your test suite:

```bash
./test-all-de.sh --test-only
```

This runs `pytest tests/` inside each container environment.

## 🎨 Comparison Report Features

The HTML report includes:
- ✅ Responsive design
- 🖼️ Click to enlarge screenshots
- 📊 Test summary statistics
- 🎨 Color-coded desktop environments
- ⌨️ Keyboard shortcuts (Esc to close modal)
- 📱 Mobile-friendly layout

## 🔍 Debugging

### Container Build Fails

Check Podman logs:
```bash
podman images  # List built images
podman ps -a   # List containers
podman logs <container-id>
```

### Screenshots Not Generated

Run container interactively:
```bash
podman run -it --rm \
  -v $PWD:/app:ro \
  -v $PWD/test-screenshots:/screenshots:rw \
  tuxtalk-test:gnome /bin/bash
```

Then manually run:
```bash
/usr/local/bin/test-runner.sh screenshot
```

### Display Issues

Check Xvfb:
```bash
# Inside container
ps aux | grep Xvfb
xdpyinfo -display :99
```

## 📦 Dependencies

**Host system:**
- Podman (or Docker)
- Bash
- xdg-open (for auto-opening reports)

**Container images:**
- Fedora base
- GTK3/GTK4
- Desktop environment packages
- Python 3 + PyGObject
- Xvfb (virtual display)

## 🚀 Performance

### Build Time (First Run)
- GNOME: ~2-3 minutes
- KDE: ~3-4 minutes
- XFCE: ~2-3 minutes
**Total: ~8-10 minutes**

### Test Time (Subsequent Runs)
- Per environment: ~5-10 seconds
- All three + report: ~30 seconds

## 🎯 Use Cases

### Before Release
Run visual tests to ensure UI looks good across DEs:
```bash
./test-all-de.sh
# Review comparison-report.html
# Fix any visual issues
# Re-test
```

### CI/CD Integration
Add to GitHub Actions:
```yaml
- name: Test across desktop environments
  run: ./test-all-de.sh --no-report
- name: Upload screenshots
  uses: actions/upload-artifact@v3
  with:
    name: screenshots
    path: test-screenshots/
```

### Quick Theme Testing
Test a CSS change:
```bash
# Make changes to prefs_style.css
./test-all-de.sh --no-build  # Fast re-test
```

## 🤝 Contributing

To add a new desktop environment:

1. Create `Dockerfile.newde`
2. Add to `build-all.sh`
3. Add to `run-tests.sh`
4. Update `generate-comparison-report.sh`

## 📚 Resources

- [Podman Documentation](https://docs.podman.io/)
- [Xvfb Guide](https://www.x.org/releases/X11R7.6/doc/man/man1/Xvfb.1.xhtml)
- [GTK Inspector](https://wiki.gnome.org/Projects/GTK/Inspector)
- [Desktop Entry Spec](https://specifications.freedesktop.org/desktop-entry-spec/)

## ⚠️ Limitations

- **No Wayland:** Containers use X11 (Xvfb) only
- **Static Screenshots:** Can't capture animations/transitions
- **No User Interaction:** Automated only, no manual testing
- **Size:** Container images are ~500MB-1GB each

## 🆘 Troubleshooting

### "No space left on device"
Podman images are large. Clean up:
```bash
podman system prune -a
```

### "Permission denied"
Ensure scripts are executable:
```bash
chmod +x docker-testing/*.sh
chmod +x test-all-de.sh
```

### "Container build timeout"
Slow network? Increase timeout or use local mirror:
```bash
# In Dockerfile
RUN dnf install -y --setopt=timeout=300 ...
```

## 📝 Notes

- Images are built locally (not pulled from registry)
- Screenshots use timestamp naming for versioning
- Report auto-refreshes when new screenshots added
- All tests run in parallel for speed

---

**Happy Testing! 🎉**

For issues or questions, see the main TuxTalk repository README.

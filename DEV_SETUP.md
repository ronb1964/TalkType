# TalkType Development Environment - FINAL SETUP

**This is the ONLY way to run TalkType in development mode.**

## Current Status

✅ `.venv` created with Python 3.13
✅ All dependencies installed (torch, faster-whisper, sounddevice, etc.)
✅ Uses system PyGObject (can't be installed in venv without python3-devel)
✅ Run script created: `run-dev.sh`

## How to Run TalkType (Dev Mode)

### Option 1: Desktop Launcher (Primary Method)
**The user has been using this from the beginning:**

Click on "TalkType (Dev)" in your application launcher, or run:
```bash
gtk-launch talktype-dev
```

Desktop file location: `~/.local/share/applications/talktype-dev.desktop`

This launcher:
- Sets `DEV_MODE=1` environment variable
- Sets proper PYTHONPATH automatically
- Uses the `.venv/bin/python` from the project
- Runs `python -m talktype.tray` to start the tray icon

### Option 2: Command Line Script
```bash
./run-dev.sh
```

This script does the same thing as the desktop launcher but from command line

## How It Works

- **Dependencies**: `.venv/` (PyTorch, faster-whisper, sounddevice, etc.)
- **PyGObject**: System package from `/usr/lib64/python3.13/site-packages`
- **TalkType code**: `src/talktype/`
- **Runner**: `run-dev.sh` sets up environment correctly

## If Something Breaks

1. **Kill all TalkType processes**:
   ```bash
   pkill -f talktype
   rm -f /run/user/$(id -u)/talktype-tray.lock
   ```

2. **Reinstall dependencies** (if needed):
   ```bash
   rm -rf .venv
   python3 -m venv .venv
   .venv/bin/pip install --upgrade pip poetry
   .venv/bin/poetry config virtualenvs.in-project true
   .venv/bin/poetry install
   ```

3. **Run again**:
   ```bash
   ./run-dev.sh
   ```

## DON'T

- ❌ Don't use `poetry run dictate-tray` (won't find PyGObject)
- ❌ Don't try to install PyGObject in venv (needs python3-devel)
- ❌ Don't use PYTHONPATH manually (run-dev.sh does it)
- ❌ Don't create multiple venvs (.venv-new, .venv-dev, etc.)

## DO

- ✅ Use `./run-dev.sh` to start TalkType
- ✅ Use `.venv/bin/pytest` to run tests
- ✅ Use `.venv/bin/python` for Python scripts (with PYTHONPATH set)

## The service won't start from tray?

The code in `src/talktype/tray.py` was fixed to detect dev mode and set PYTHONPATH automatically when starting the dictation service. It should work now.

If it doesn't, check:
```bash
# See if service starts manually
PYTHONPATH=./src .venv/bin/python -m talktype.app
```

---

**This setup is FINAL. Don't change it unless you have a good reason and test completely.**

# How to Restore Working Dev Environment

You had TalkType working last night. Here's how to get back to that:

## What You Need

You already have `.venv` with all dependencies installed (torch, faster-whisper, etc.)

The only issue: PyGObject (GTK) must come from the system.

## To Run TalkType NOW

```bash
./run-dev.sh
```

That's it. The script sets the right PYTHONPATH and runs the tray.

## If It Doesn't Work

1. **Kill any running instances**:
   ```bash
   pkill -f talktype
   rm -f /run/user/$(id -u)/talktype-tray.lock
   ```

2. **Run it**:
   ```bash
   ./run-dev.sh
   ```

## How Last Night's Version Worked

You likely ran it from your desktop launcher which had the right environment set up, or you had a working venv that I broke by trying to "fix" things.

## The Working Setup

- `.venv/` has all Python packages
- System has PyGObject at `/usr/lib64/python3.13/site-packages`
- `run-dev.sh` combines both with PYTHONPATH
- `tray.py` was fixed to auto-set PYTHONPATH when starting the service

## If Service Won't Start from Tray

The tray should auto-start the dictation service. I fixed it to set PYTHONPATH correctly.

If it still fails, the fix is in `src/talktype/tray.py` line 242-248 where it sets absolute paths.

---

**Just run `./run-dev.sh` and it should work.**

If not, tell me the EXACT error and I'll fix JUST that one thing.

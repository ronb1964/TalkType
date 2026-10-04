"""The one place that knows how to start and stop the dictation service.

The service is launched from two places — the tray (at startup and on "Restart
Service") and Preferences (on Apply/OK). They used to hand-roll the spawn
separately, and only the tray's copy set GDK_BACKEND.

That was invisible while AppRun exported GDK_BACKEND=x11 for the whole app, so
every process inherited it. Once the backend was scoped to the tray's spawn (so
GTK dropdowns would work on Wayland), a service restarted from Preferences
inherited Preferences' environment instead — native Wayland — where
gtk_window_move() is ignored. The recording indicator then centred itself no
matter what indicator_position said, and only a full quit-and-relaunch fixed
it, because that put the tray back in charge of launching.

Keeping the spawn in one place is the actual fix; the backend is just the
symptom that exposed the duplication.
"""

import logging
import os
import signal
import subprocess
import sys

logger = logging.getLogger(__name__)

# XWayland first: the recording indicator positions itself with
# gtk_window_move(), which XWayland honours and native Wayland ignores.
# The fallback matters — pinned to bare "x11", GTK cannot initialise on a
# system without XWayland and the service dies on launch, costing dictation
# entirely to protect a cosmetic window position.
SERVICE_GDK_BACKEND = "x11,wayland"

# Python site-package paths to expose in dev mode, so the service can find the
# system PyGObject that the venv cannot see.
_DEV_SITE_PACKAGES = (
    "/usr/lib64/python3.14/site-packages",
    "/usr/lib/python3.14/site-packages",
    "/usr/lib64/python3.13/site-packages",
    "/usr/lib/python3.13/site-packages",
)


def is_service_argv(argv) -> bool:
    """True if *argv* (a process's argument list) is the dictation service.

    The service only ever runs one of two ways:
      * ``<python> -m talktype.app`` — dev checkouts, the AppImage, the .deb and
        .rpm (which repackage the AppImage) and the Flatpak.
      * the ``dictate`` console script from a pip install, which the kernel
        runs as ``<python> /path/bin/dictate`` (or ``/path/bin/dictate``).

    So this compares whole arguments, never substrings of the command line.
    A substring match ("talktype.app" anywhere) is how a shell running
    ``bash -c "pgrep -f talktype.app"`` once passed for the service: the tray
    cached that shell's PID, and toggle_recording would have sent SIGUSR1 to
    it, which kills a process that doesn't handle it. Exact arguments also keep
    the tray safe: "-m talktype.tray" and bin/dictate-tray never match.
    """
    argv = list(argv)
    for i, arg in enumerate(argv[:-1]):
        if arg == "-m" and argv[i + 1] == "talktype.app":
            return True
    if not argv:
        return False
    # The program itself, or the script a Python interpreter is running.
    # Anywhere else "dictate" is just a file another program was handed
    # (`vim .../bin/dictate`).
    if os.path.basename(argv[0]) == "dictate":
        return True
    return (len(argv) > 1 and os.path.basename(argv[0]).startswith("python")
            and os.path.basename(argv[1]) == "dictate")


def _read_argv(pid):
    """A process's argument list from /proc, or None if it can't be read."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read()
    except OSError:
        return None  # gone already, or not ours to read
    # cmdline is NUL-separated with a trailing NUL; kernel threads have none.
    return [a.decode(errors="ignore") for a in raw.split(b"\0") if a]


def is_service_pid(pid) -> bool:
    """True if *pid* is a running dictation service owned by this user."""
    try:
        if os.stat(f"/proc/{pid}").st_uid != os.getuid():
            return False
    except OSError:
        return False
    argv = _read_argv(pid)
    return bool(argv) and is_service_argv(argv)


def find_service_pids():
    """PIDs of every dictation service this user is running, read from /proc.

    No subprocess: the tray polls this, and pgrep/pkill only offer substring
    matching on the joined command line, which is the bug is_service_argv fixes.
    """
    me = os.getpid()
    try:
        entries = os.listdir("/proc")
    except OSError:
        return []
    return [
        int(e) for e in entries
        if e.isdigit() and int(e) != me and is_service_pid(int(e))
    ]


def stop_dictation_service(force: bool = False) -> None:
    """Terminate the dictation service, and only the dictation service.

    *force* sends SIGKILL instead of SIGTERM; first-run onboarding uses it to
    guarantee a stale service is gone before the welcome flow starts.

    Never raises. Both callers are cleanup paths where failing to kill a service
    is a far better outcome than propagating an exception — one of them is the
    quit handler, and the other is the first thing a new user ever sees.
    """
    sig = signal.SIGKILL if force else signal.SIGTERM
    try:
        pids = find_service_pids()
    except Exception as e:
        logger.warning(f"Could not look for the dictation service: {e}")
        return
    for pid in pids:
        try:
            os.kill(pid, sig)
        except OSError:
            pass  # exited between the scan and the kill
    # SIGTERM/SIGKILL skip the service's exit hooks, so hand its hotkeys back
    # to the desktop from here. Otherwise KWin would keep swallowing F8 with
    # dictation off.
    try:
        from . import kwin_hotkeys
        kwin_hotkeys.release()
    except Exception as e:
        logger.debug(f"Could not release the KWin hotkeys: {e}")


def build_service_env(base_env=None, dev_pythonpath=None):
    """Return the environment the dictation service must be started with.

    Always overrides GDK_BACKEND rather than deferring to what the caller
    happens to have. Preferences runs on native Wayland by design, so
    inheriting its backend is precisely the bug this module exists to prevent.
    """
    env = dict(os.environ if base_env is None else base_env)
    env["GDK_BACKEND"] = SERVICE_GDK_BACKEND
    if dev_pythonpath:
        env["PYTHONPATH"] = dev_pythonpath
    return env


def _dictate_script_path():
    """Path to the AppImage's bin/dictate, or None outside an AppImage.

    __file__ is usr/src/talktype/service_launcher.py → usr/bin/dictate
    """
    src_dir = os.path.dirname(__file__)
    usr_dir = os.path.dirname(os.path.dirname(src_dir))
    path = os.path.join(usr_dir, "bin", "dictate")
    return path if os.path.exists(path) else None


def dev_pythonpath():
    """PYTHONPATH for running from a source checkout, or None for the AppImage."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    src_dir = os.path.join(project_root, "src")
    if not os.path.exists(src_dir):
        return None
    return ":".join([os.path.abspath(src_dir), *_DEV_SITE_PACKAGES])


def launch_dictation_service():
    """Start the dictation service. Returns the Popen object, or None on failure.

    Callers must not spawn it themselves — tests/test_service_launch_parity.py
    fails if they do, because that is how the two paths drifted apart.
    """
    dictate_script = _dictate_script_path()

    if dictate_script:
        env = build_service_env()
        proc = subprocess.Popen([dictate_script], env=env)
        logger.info(f"Started dictation service via {dictate_script} (PID {proc.pid})")
        return proc

    # Dev mode: run the module directly with src/ and system PyGObject on the path.
    env = build_service_env(dev_pythonpath=dev_pythonpath())
    proc = subprocess.Popen([sys.executable, "-m", "talktype.app"], env=env)
    logger.info(f"Started dictation service via python -m talktype.app (PID {proc.pid})")
    return proc

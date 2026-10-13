"""The one place that knows how to start and stop the dictation service.

The service is launched from the tray (at startup and on "Restart Service")
and from Preferences (on Apply/OK). Both go through here so the service always
gets the same environment, in particular its own GDK_BACKEND: Preferences runs
on native Wayland, where gtk_window_move() is ignored and the recording
indicator could not be positioned.
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

# Hotkey test mode (Preferences, Test Hotkeys). While this flag file is fresh,
# the service reports hotkey presses instead of recording. Preferences touches
# it every HOTKEY_TEST_REFRESH_S while its dialog is open and removes it on
# close. One older than HOTKEY_TEST_LEASE_S is ignored, so a Preferences that
# crashed or was killed can't leave dictation switched off.
HOTKEY_TEST_LEASE_S = 6.0
HOTKEY_TEST_REFRESH_S = 2


def hotkey_test_flag_path() -> str:
    """Where Preferences keeps the hotkey test flag for the service to see."""
    from .config import get_data_dir
    return os.path.join(get_data_dir(), ".hotkey_test_mode")


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
      * ``<python> -m tuxtalk.app`` — dev checkouts, the AppImage, the .deb and
        .rpm (which repackage the AppImage) and the Flatpak.
      * the ``dictate`` console script from a pip install, which the kernel
        runs as ``<python> /path/bin/dictate`` (or ``/path/bin/dictate``).

    So this compares whole arguments, never substrings of the command line.
    A substring match ("tuxtalk.app" anywhere) would accept a shell running
    ``bash -c "pgrep -f tuxtalk.app"``, and the tray's toggle_recording would
    send it SIGUSR1, which kills a process that doesn't handle it. Exact
    arguments also keep the tray safe: "-m tuxtalk.tray" and bin/dictate-tray
    never match.
    """
    argv = list(argv)
    for i, arg in enumerate(argv[:-1]):
        # talktype.app: the service from before the 0.15.0 rename, which a
        # 0.14.x in-app update leaves running (it holds the shared lock).
        if arg == "-m" and argv[i + 1] in ("tuxtalk.app", "talktype.app"):
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


def is_pre_rename_service_argv(argv) -> bool:
    """True for a dictation service from before the 0.15.0 rename
    (``-m talktype.app``): old code that should give way to the new version."""
    argv = list(argv)
    return any(a == "-m" and b == "talktype.app" for a, b in zip(argv, argv[1:]))


def pre_rename_service_pids():
    """PIDs of running pre-rename (TalkType) dictation services."""
    return [pid for pid in find_service_pids()
            if is_pre_rename_service_argv(_read_argv(pid) or [])]


def is_pre_rename_tray_argv(argv) -> bool:
    """True for a tray from before the 0.15.0 rename (``-m talktype.tray``).
    It shares TuxTalk's single-instance lock, so it keeps TuxTalk from starting."""
    argv = list(argv)
    return any(a == "-m" and b == "talktype.tray" for a, b in zip(argv, argv[1:]))


def pre_rename_tray_pids():
    """PIDs of this user's running pre-rename (TalkType) trays.

    Exact arguments, as for the service, so nothing but an old tray matches.
    """
    me = os.getpid()
    try:
        entries = os.listdir("/proc")
    except OSError:
        return []
    pids = []
    for entry in entries:
        if not entry.isdigit() or int(entry) == me:
            continue
        pid = int(entry)
        try:
            if os.stat(f"/proc/{pid}").st_uid != os.getuid():
                continue
        except OSError:
            continue
        if is_pre_rename_tray_argv(_read_argv(pid) or []):
            pids.append(pid)
    return pids


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
    matching on the joined command line, which is too loose (see
    is_service_argv).
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
    happens to have: Preferences runs on native Wayland by design, and the
    service must not inherit that.
    """
    env = dict(os.environ if base_env is None else base_env)
    env["GDK_BACKEND"] = SERVICE_GDK_BACKEND
    if dev_pythonpath:
        env["PYTHONPATH"] = dev_pythonpath
    return env


def dev_pythonpath():
    """PYTHONPATH for running from a source checkout, or None for the AppImage."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    src_dir = os.path.join(project_root, "src")
    if not os.path.exists(src_dir):
        return None
    return ":".join([os.path.abspath(src_dir), *_DEV_SITE_PACKAGES])


def launch_dictation_service():
    """Start the dictation service. Returns the Popen object, or None on failure.

    Callers must not spawn it themselves, so every path starts it the same way
    (tests/test_service_launch_parity.py checks this).
    """
    # Every install runs the module. The AppImage, .deb and .rpm child inherits
    # PYTHONPATH and the library paths from dictate-tray; in a source checkout
    # dev_pythonpath() adds src/ and the system PyGObject.
    env = build_service_env(dev_pythonpath=dev_pythonpath())
    proc = subprocess.Popen([sys.executable, "-m", "tuxtalk.app"], env=env)
    logger.info(f"Started dictation service via python -m tuxtalk.app (PID {proc.pid})")
    return proc


def launch_preferences(tab=None):
    """Start the Preferences window as its own process; returns the Popen.

    Shared by the tray and the first-run screens. Unlike the service it keeps
    the caller's GDK_BACKEND: Preferences runs natively, so its dropdowns work
    on Wayland.
    """
    env = os.environ.copy()
    pythonpath = dev_pythonpath()
    if pythonpath:
        env["PYTHONPATH"] = pythonpath
    cmd = [sys.executable, "-m", "tuxtalk.prefs"]
    if tab:
        cmd.append(f"--tab={tab}")
    return subprocess.Popen(cmd, env=env)

"""
Asking an already-open Preferences window to come to the front.

Preferences runs as its own process and allows one instance (pidfile). A
second "open" (tray menu, GNOME extension via the tray, or a second launch)
signals the running one instead of doing nothing: SIGUSR1 = come to the
front, SIGUSR2 = come to the front on the Updates tab.

Preferences installs its handlers before it writes the pidfile, so a pid read
from the pidfile is always ready for the signal; SIGUSR1's default action is
to terminate, so signalling a process that is still starting would kill it.
"""
import os
import signal

FRONT = signal.SIGUSR1
FRONT_UPDATES = signal.SIGUSR2


def pidfile_path():
    base = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return os.path.join(base, "talktype-prefs.pid")


def running_pid():
    """Pid of the open Preferences window, or None."""
    try:
        with open(pidfile_path()) as f:
            pid = int(f.read().strip() or "0")
        if pid > 0:
            os.kill(pid, 0)
            return pid
    except (OSError, ValueError):
        pass
    return None


def bring_to_front(pid, tab=None):
    """Ask Preferences (*pid*) to come to the front. Returns True if sent."""
    try:
        os.kill(pid, FRONT_UPDATES if tab == "updates" else FRONT)
        return True
    except OSError:
        return False

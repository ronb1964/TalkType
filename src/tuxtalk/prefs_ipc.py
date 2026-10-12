"""
Asking an already-open Preferences window to come to the front.

Preferences runs as its own process and allows one instance (pidfile). A
second "open" (tray menu, GNOME extension via the tray, or a second launch)
signals the running one instead of doing nothing: SIGUSR1 = come to the
front. To also switch tab (the tray's "Your Stats...", or the update
notification's Updates tab), the tab name is written to a small request file
first, which Preferences reads when the signal arrives.

Preferences installs its handlers before it writes the pidfile, so a pid read
from the pidfile is always ready for the signal; SIGUSR1's default action is
to terminate, so signalling a process that is still starting would kill it.
"""
import os
import signal

FRONT = signal.SIGUSR1


def pidfile_path():
    base = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return os.path.join(base, "talktype-prefs.pid")


def _tab_request_path():
    return pidfile_path() + ".tab"


def take_tab_request():
    """The tab the last front request asked for (then forgotten), or None."""
    try:
        with open(_tab_request_path()) as f:
            tab = f.read().strip()
        os.remove(_tab_request_path())
        return tab or None
    except OSError:
        return None


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
    """Ask Preferences (*pid*) to come to the front, on *tab* if given.
    Returns True if the request was sent."""
    try:
        if tab:
            with open(_tab_request_path(), "w") as f:
                f.write(tab)
        else:
            os.remove(_tab_request_path())        # don't act on a stale request
    except OSError:
        pass
    try:
        os.kill(pid, FRONT)
        return True
    except OSError:
        return False

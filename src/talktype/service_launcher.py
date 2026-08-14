"""The one place that knows how to start the dictation service.

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

"""TalkType - AI-powered speech recognition and dictation for Wayland"""

import ctypes.util
import os

__version__ = "0.14.2"

# Where the AppImage (and the .deb/.rpm made from it) keeps its own PortAudio:
# <root>/usr/src/talktype/ -> <root>/usr/lib/portaudio/. In a dev checkout or
# the Flatpak this folder doesn't exist and nothing changes.
_BUNDLED_PORTAUDIO_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "lib", "portaudio")


def _use_bundled_portaudio(lib_dir=_BUNDLED_PORTAUDIO_DIR):
    """Let sounddevice fall back to the bundled PortAudio.

    sounddevice finds PortAudio with ctypes.util.find_library("portaudio"),
    which only consults the system's linker cache, so a copy inside the
    AppImage is invisible to it. On a system without libportaudio that meant
    no microphone at all (AppImageHub's test, 2026-09-26).

    The system's PortAudio still wins when there is one, so existing installs
    behave exactly as before. Runs on package import, which is always before
    sounddevice is imported.
    """
    bundled = os.path.join(lib_dir, "libportaudio.so.2")
    if not os.path.isfile(bundled):
        return
    system_find_library = ctypes.util.find_library

    def find_library(name):
        found = system_find_library(name)
        if found is None and name == "portaudio":
            return os.path.normpath(bundled)
        return found

    ctypes.util.find_library = find_library


_use_bundled_portaudio()

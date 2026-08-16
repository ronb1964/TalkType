"""Text-injection backends.

TalkType needs to type transcribed text into whatever app is focused. Outside a
Flatpak it uses ydotool (Backend A); inside a Flatpak the uinput path is blocked,
so it types through the RemoteDesktop portal + libei (Backend B). The backend is
chosen once at startup by FLATPAK_ID and hidden behind a single method so the
recording core never knows which one is in use.
"""
import os


class OutputBackend:
    """Types text into the focused application. Returns True if the text was
    actually delivered, False if injection failed (never raises — the caller
    surfaces a plain-language notice on False)."""

    def type_text(self, text: str) -> bool:
        raise NotImplementedError


class YdotoolOutputBackend(OutputBackend):
    """Backend A: the existing ydotool path, unchanged."""

    def type_text(self, text: str) -> bool:
        from . import app
        return app._type_text(text)


class LibeiOutputBackend(OutputBackend):
    """Backend B: type via the RemoteDesktop portal + libei (Flatpak)."""

    def type_text(self, text: str) -> bool:
        raise NotImplementedError("implemented in BB-5")


def get_output_backend(flatpak_id=None) -> OutputBackend:
    """Pick the output backend. flatpak_id=None reads the real environment."""
    if flatpak_id is None:
        flatpak_id = os.environ.get("FLATPAK_ID", "")
    return LibeiOutputBackend() if flatpak_id else YdotoolOutputBackend()

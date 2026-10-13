"""Desktop notifications through libnotify, shared by the tray and the service.

This module has no heavy imports on purpose: the tray shows notices too, and
importing app.py for them would load the whole dictation engine (numpy,
faster_whisper, torch) into the tray for the rest of the session.
"""

_ready = None   # None until the first notice; then True or False


def _init():
    """Initialise libnotify on first use. It is optional: without it, notices are skipped."""
    global _ready
    if _ready is None:
        try:
            import gi
            gi.require_version("Notify", "0.7")
            from gi.repository import Notify
            _ready = bool(Notify.init("TuxTalk"))
        except Exception:
            _ready = False
    return _ready


def notify(title: str, body: str):
    if not _init():
        return
    try:
        from gi.repository import Notify
        Notify.Notification.new(title, body).show()
    except Exception:
        pass

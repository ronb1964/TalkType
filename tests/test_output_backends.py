"""The Ydotool backend must keep delegating to app._type_text so the non-Flatpak
typing path is behaviorally unchanged."""


def test_ydotool_backend_delegates_to_type_text(monkeypatch):
    from talktype import app
    from talktype.output_backends import YdotoolOutputBackend
    calls = []
    monkeypatch.setattr(app, "_type_text", lambda t: calls.append(t) or True)
    assert YdotoolOutputBackend().type_text("hello") is True
    assert calls == ["hello"]


def test_libei_backend_returns_false_when_handshake_fails(monkeypatch):
    # type_text must never raise — it returns False so the caller can notify.
    from talktype.output_backends import LibeiOutputBackend
    b = LibeiOutputBackend()
    monkeypatch.setattr(b, "_run_handshake", lambda: (None, None))
    assert b.type_text("hi") is False


def test_libei_backend_types_via_fresh_session(monkeypatch):
    # A fresh RemoteDesktop/EIS session per call: handshake -> LibeiSession ->
    # pump_until_ready -> type_string, then the session is closed.
    import talktype.libei_ctypes as libei_ctypes
    from talktype.output_backends import LibeiOutputBackend
    b = LibeiOutputBackend()
    typed = []
    closed = []

    class FakeSession:
        def __init__(self, fd):
            self.fd = fd

        def pump_until_ready(self):
            return True

        def type_string(self, t):
            typed.append(t)
            return True

    monkeypatch.setattr(b, "_run_handshake", lambda: (-1, "/org/session/1"))
    monkeypatch.setattr(b, "_close_session", lambda p: closed.append(p))
    monkeypatch.setattr(libei_ctypes, "LibeiSession", FakeSession)

    assert b.type_text("hello") is True
    assert typed == ["hello"]
    assert closed == ["/org/session/1"]  # session cleaned up


def test_output_backend_accessor_returns_ydotool_on_host(monkeypatch):
    # No FLATPAK_ID on the host -> ydotool backend.
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    from talktype import app
    app._OUTPUT_BACKEND = None  # reset the process cache for the test
    from talktype.output_backends import YdotoolOutputBackend
    assert isinstance(app._output_backend(), YdotoolOutputBackend)

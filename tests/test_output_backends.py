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


def test_save_token_creates_missing_data_dir(tmp_path, monkeypatch):
    # On a fresh CPU-only Flatpak install the data dir (data/TalkType/) doesn't
    # exist yet — nothing has written CUDA libs or the first-run flag there. If
    # _save_token can't create it, the RemoteDesktop restore token never
    # persists and GNOME re-prompts "Allow remote interaction?" on every single
    # dictation. It must create its parent dir like every other data-dir writer.
    from talktype.output_backends import LibeiOutputBackend
    b = LibeiOutputBackend()
    token_path = tmp_path / "TalkType" / "remote_desktop_token"  # parent missing
    monkeypatch.setattr(b, "_token_path", lambda: str(token_path))

    b._save_token("restore-token-abc")

    assert token_path.exists(), "token must be written even when data dir was absent"
    assert token_path.read_text() == "restore-token-abc"
    assert b._load_token() == "restore-token-abc"


def test_output_backend_accessor_returns_ydotool_on_host(monkeypatch):
    # No FLATPAK_ID on the host -> ydotool backend.
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    from talktype import app
    app._OUTPUT_BACKEND = None  # reset the process cache for the test
    from talktype.output_backends import YdotoolOutputBackend
    assert isinstance(app._output_backend(), YdotoolOutputBackend)


# --- Editing key-combos must route through the backend, not hardcoded ydotool ---
# The 'delete everything' and char-undo commands press special keys (Ctrl+A,
# Backspace). They used to call ydotool directly, which does nothing in the
# Flatpak sandbox (no ydotoold), so the commands silently failed there.

def test_ydotool_backend_select_all_delete_delegates(monkeypatch):
    from talktype import app
    from talktype.output_backends import YdotoolOutputBackend
    calls = []
    monkeypatch.setattr(app, "_send_select_all_delete", lambda: calls.append("clear") or True)
    assert YdotoolOutputBackend().select_all_delete() is True
    assert calls == ["clear"]


def test_ydotool_backend_backspaces_delegates(monkeypatch):
    from talktype import app
    from talktype.output_backends import YdotoolOutputBackend
    calls = []
    monkeypatch.setattr(app, "_send_backspaces", lambda n: calls.append(n) or True)
    assert YdotoolOutputBackend().backspaces(5) is True
    assert calls == [5]


def test_libei_backend_select_all_delete_via_fresh_session(monkeypatch):
    import talktype.libei_ctypes as libei_ctypes
    from talktype.output_backends import LibeiOutputBackend
    b = LibeiOutputBackend()
    called, closed = [], []

    class FakeSession:
        def __init__(self, fd):
            pass

        def pump_until_ready(self):
            return True

        def select_all_delete(self):
            called.append("clear")
            return True

    monkeypatch.setattr(b, "_run_handshake", lambda: (-1, "/org/session/1"))
    monkeypatch.setattr(b, "_close_session", lambda p: closed.append(p))
    monkeypatch.setattr(libei_ctypes, "LibeiSession", FakeSession)

    assert b.select_all_delete() is True
    assert called == ["clear"]
    assert closed == ["/org/session/1"]  # session cleaned up


def test_libei_backend_backspaces_via_fresh_session(monkeypatch):
    import talktype.libei_ctypes as libei_ctypes
    from talktype.output_backends import LibeiOutputBackend
    b = LibeiOutputBackend()
    got, closed = [], []

    class FakeSession:
        def __init__(self, fd):
            pass

        def pump_until_ready(self):
            return True

        def backspaces(self, n):
            got.append(n)
            return True

    monkeypatch.setattr(b, "_run_handshake", lambda: (-1, "/org/session/2"))
    monkeypatch.setattr(b, "_close_session", lambda p: closed.append(p))
    monkeypatch.setattr(libei_ctypes, "LibeiSession", FakeSession)

    assert b.backspaces(4) is True
    assert got == [4]
    assert closed == ["/org/session/2"]


def test_handle_undo_everything_routes_through_backend(monkeypatch):
    # 'delete everything' must call the backend's select_all_delete, so it works
    # on the Flatpak (libei) exactly like on the host (ydotool).
    from talktype import app
    monkeypatch.setattr(app, "detect_undo_command", lambda raw: ("everything", 1))
    monkeypatch.setattr(app, "_beep", lambda *a, **k: None)
    monkeypatch.setattr(app, "_notify", lambda *a, **k: None)
    calls = []

    class FakeBackend:
        def select_all_delete(self):
            calls.append("clear")
            return True

    monkeypatch.setattr(app, "_output_backend", lambda: FakeBackend())
    assert app._handle_undo("delete everything", False, False) is True
    assert calls == ["clear"]


def test_handle_undo_char_undo_routes_backspaces_through_backend(monkeypatch):
    # Character-level undo must send its backspaces through the backend too.
    from talktype import app
    monkeypatch.setattr(app, "detect_undo_command", lambda raw: ("word", 1))
    monkeypatch.setattr(app, "_beep", lambda *a, **k: None)
    monkeypatch.setattr(app, "_notify", lambda *a, **k: None)
    app.state.last_inserted_text = "hello world"
    got = []

    class FakeBackend:
        def backspaces(self, n):
            got.append(n)
            return True

    monkeypatch.setattr(app, "_output_backend", lambda: FakeBackend())
    assert app._handle_undo("undo that", False, False) is True
    assert got and got[0] > 0  # deleted a positive number of characters


def test_flatpak_electron_app_types_via_libei_not_ydotool_fasttype(monkeypatch):
    # On the Flatpak, dictating into an Electron app (Claude Desktop) must NOT
    # attempt the ydotool fast-type path (dead in the sandbox). It types through
    # the libei backend directly, keeping only the tab→spaces safety (a real Tab
    # jumps focus to Claude Desktop's Send button).
    from talktype import app
    monkeypatch.setenv("FLATPAK_ID", "io.github.ronb1964.TalkType")
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: "Claude")
    fast_calls = []
    monkeypatch.setattr(app, "_type_text_fast", lambda *a, **k: fast_calls.append(a) or True)
    typed = []

    class FakeBackend:
        def type_text(self, t):
            typed.append(t)
            return True

    monkeypatch.setattr(app, "_output_backend", lambda: FakeBackend())
    app._inject_text("line1\tindented", "auto", 0.0)

    assert fast_calls == [], "ydotool fast-type must not run on the Flatpak"
    assert typed == ["line1    indented"], "tab→4 spaces, delivered via libei"

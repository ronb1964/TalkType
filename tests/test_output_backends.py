"""The Ydotool backend must keep delegating to app._type_text so the non-Flatpak
typing path is behaviorally unchanged."""


def test_ydotool_backend_delegates_to_type_text(monkeypatch):
    from talktype import app
    from talktype.output_backends import YdotoolOutputBackend
    calls = []
    monkeypatch.setattr(app, "_type_text", lambda t: calls.append(t) or True)
    assert YdotoolOutputBackend().type_text("hello") is True
    assert calls == ["hello"]


def test_output_backend_accessor_returns_ydotool_on_host(monkeypatch):
    # No FLATPAK_ID on the host -> ydotool backend.
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    from talktype import app
    app._OUTPUT_BACKEND = None  # reset the process cache for the test
    from talktype.output_backends import YdotoolOutputBackend
    assert isinstance(app._output_backend(), YdotoolOutputBackend)

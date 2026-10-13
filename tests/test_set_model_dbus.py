"""SetModel over D-Bus must actually change the model.

The D-Bus interface declares SetModel and the GNOME extension's interface XML
lists it, so both sides must really implement it:

  * DBusService._dispatch only forwards when hasattr(app, name) is true, so
    TrayAppInstance — the object the tray registers — needs set_model, or the
    call is silently dropped with no error anywhere.
  * The service's implementation must save through config.save_config(), not
    to a settings.json this app never reads.
"""

from types import SimpleNamespace

from tuxtalk.tray import DictationTray


def test_the_tray_exposes_set_model_to_dbus():
    """DBusService._dispatch drops calls for methods the app lacks."""
    assert hasattr(DictationTray, "set_model"), \
        "SetModel is advertised over D-Bus but the tray cannot receive it"


def test_set_model_writes_the_model_and_restarts(monkeypatch):
    saved = {}
    restarted = []
    emitted = []

    cfg = SimpleNamespace(model="small", device="cpu")
    monkeypatch.setattr("tuxtalk.config.load_config", lambda: cfg)
    monkeypatch.setattr("tuxtalk.config.save_config",
                        lambda c: saved.update(model=c.model))

    tray = SimpleNamespace(
        update_menu_display=lambda: None,
        _emit_model_changed=lambda m: emitted.append(m),
        restart_service=lambda _: restarted.append(True),
    )

    DictationTray.set_model(tray, "large-v3")

    assert saved.get("model") == "large-v3", "the model was never persisted"
    assert emitted == ["large-v3"], "the GNOME extension was not told"
    assert restarted, "the service was not restarted to pick up the new model"


def test_set_model_rejects_an_unknown_model(monkeypatch):
    """A typo over D-Bus must not write a model the service cannot load."""
    saved = {}
    cfg = SimpleNamespace(model="small", device="cpu")
    monkeypatch.setattr("tuxtalk.config.load_config", lambda: cfg)
    monkeypatch.setattr("tuxtalk.config.save_config",
                        lambda c: saved.update(model=c.model))

    tray = SimpleNamespace(
        update_menu_display=lambda: None,
        _emit_model_changed=lambda m: None,
        restart_service=lambda _: None,
    )

    DictationTray.set_model(tray, "not-a-real-model")

    assert saved == {}, "wrote an unknown model to the config"


# --- the dictation service's own implementation -----------------------------

def test_the_service_does_not_write_a_phantom_settings_json():
    """AppInstance.set_model must not write ~/.config/talktype/settings.json,
    a file this app never reads. Real settings go to config.toml through
    config.save_config(); anything else is gone after the restart it tells
    the user is required.

    Checked structurally because AppInstance is defined inline inside app.py's
    startup path and cannot be constructed in isolation.
    """
    import ast
    import pathlib

    src = (pathlib.Path(__file__).resolve().parent.parent
           / "src" / "tuxtalk" / "app.py").read_text()
    tree = ast.parse(src)

    # Docstrings may mention the path when explaining the rule; only real
    # string values in code count.
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docstrings.add(id(first.value))

    offenders = [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and id(n) not in docstrings and "settings.json" in n.value
    ]

    assert not offenders, (
        f"app.py still references the phantom settings.json in code: {offenders}"
    )

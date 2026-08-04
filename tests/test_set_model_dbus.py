"""SetModel over D-Bus must actually change the model.

The D-Bus interface declares SetModel and the GNOME extension's interface XML
lists it, but nothing implemented it where it counts:

  * DBusService._dispatch only forwards when hasattr(app, name) is true, and
    TrayAppInstance — the object the tray registers — had no set_model, so
    the call was silently dropped with no error anywhere.
  * The one implementation that did exist wrote to
    ~/.config/talktype/settings.json, a JSON path this app has never read;
    its real settings live in ~/.config/TalkType/config.toml.

So the method existed, was advertised, and did nothing on either side.
"""

from types import SimpleNamespace

from talktype.tray import DictationTray


def test_the_tray_exposes_set_model_to_dbus():
    """DBusService._dispatch drops calls for methods the app lacks."""
    assert hasattr(DictationTray, "set_model"), \
        "SetModel is advertised over D-Bus but the tray cannot receive it"


def test_set_model_writes_the_model_and_restarts(monkeypatch):
    saved = {}
    restarted = []
    emitted = []

    cfg = SimpleNamespace(model="small", device="cpu")
    monkeypatch.setattr("talktype.config.load_config", lambda: cfg)
    monkeypatch.setattr("talktype.config.save_config",
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
    monkeypatch.setattr("talktype.config.load_config", lambda: cfg)
    monkeypatch.setattr("talktype.config.save_config",
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
    """app.py's AppInstance.set_model wrote to ~/.config/talktype/settings.json
    — a JSON file this app has never read or written. Real settings live in
    ~/.config/TalkType/config.toml, reached through config.save_config(). So
    the model "change" landed nowhere and was gone after the restart it told
    the user was required.

    Checked structurally because AppInstance is defined inline inside app.py's
    startup path and cannot be constructed in isolation.
    """
    import ast
    import pathlib

    src = (pathlib.Path(__file__).resolve().parent.parent
           / "src" / "talktype" / "app.py").read_text()
    tree = ast.parse(src)

    # Docstrings may legitimately mention the old path when explaining the
    # bug; only real string values in code count.
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

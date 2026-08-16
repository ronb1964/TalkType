"""The tray singleton lock must be sandbox-private inside a Flatpak.

Flatpak shares XDG_RUNTIME_DIR (/run/user/N) with the host, so a host/AppImage
tray's `talktype-tray.lock` is visible inside the sandbox. The Flatpak instance
then acquires-fails and exits as "already running" — the app never starts. Flatpak
provides a private per-app tmpfs dir at $XDG_RUNTIME_DIR/app/$FLATPAK_ID; the lock
must live there in a Flatpak so it never collides with a host instance. On the
host (no FLATPAK_ID) the location is unchanged — Backend A behavior is untouched.
"""

import importlib


def _tray():
    return importlib.import_module("talktype.tray")


def test_runtime_dir_is_app_private_inside_flatpak(monkeypatch, tmp_path):
    tray = _tray()
    run = tmp_path / "run"
    app_dir = run / "app" / "io.github.ronb1964.TalkType"
    app_dir.mkdir(parents=True)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(run))
    monkeypatch.setenv("FLATPAK_ID", "io.github.ronb1964.TalkType")

    assert tray._runtime_dir() == str(app_dir), (
        "inside a Flatpak the lock dir must be the private per-app runtime "
        "subdir, or the host's lock leaks in and the app exits as a duplicate"
    )


def test_runtime_dir_falls_back_when_app_subdir_absent(monkeypatch, tmp_path):
    """If the per-app subdir somehow isn't present, use the base dir rather than
    a path that doesn't exist."""
    tray = _tray()
    run = tmp_path / "run"
    run.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(run))
    monkeypatch.setenv("FLATPAK_ID", "io.github.ronb1964.TalkType")

    assert tray._runtime_dir() == str(run)


def test_runtime_dir_unchanged_on_host(monkeypatch, tmp_path):
    tray = _tray()
    run = tmp_path / "run"
    run.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(run))
    monkeypatch.delenv("FLATPAK_ID", raising=False)

    assert tray._runtime_dir() == str(run)


# app.py carries its own identical singleton lock (the dictation service). It must
# get the same sandbox-private treatment or the Flatpak's service subprocess
# collides with a host service and dictation never starts.


def _app():
    return importlib.import_module("talktype.app")


def test_app_runtime_dir_is_app_private_inside_flatpak(monkeypatch, tmp_path):
    app = _app()
    run = tmp_path / "run"
    app_dir = run / "app" / "io.github.ronb1964.TalkType"
    app_dir.mkdir(parents=True)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(run))
    monkeypatch.setenv("FLATPAK_ID", "io.github.ronb1964.TalkType")

    assert app._runtime_dir() == str(app_dir)


def test_app_runtime_dir_unchanged_on_host(monkeypatch, tmp_path):
    app = _app()
    run = tmp_path / "run"
    run.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(run))
    monkeypatch.delenv("FLATPAK_ID", raising=False)

    assert app._runtime_dir() == str(run)

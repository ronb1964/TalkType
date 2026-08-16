"""Inside a Flatpak the app must use its private per-app XDG dirs, not the host's.

Flatpak keeps XDG_CONFIG_HOME / XDG_DATA_HOME pointed at the sandbox-private
~/.var/app/<id>/{config,data} even when the user has granted --filesystem=home
(a common global override for GTK theming). If the app used HOME-based
~/.config / ~/.local/share, that home grant would make it read the HOST install's
config (wrong model, `.first_run_done` already set so onboarding is skipped).
Gating on FLATPAK_ID keeps host/dev behavior byte-for-byte unchanged.
"""

import importlib


def _config():
    return importlib.import_module("talktype.config")


def test_data_home_is_xdg_inside_flatpak(monkeypatch, tmp_path):
    cfg = _config()
    monkeypatch.setenv("FLATPAK_ID", "io.github.ronb1964.TalkType")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert cfg._data_home() == str(tmp_path / "data")


def test_config_home_is_xdg_inside_flatpak(monkeypatch, tmp_path):
    cfg = _config()
    monkeypatch.setenv("FLATPAK_ID", "io.github.ronb1964.TalkType")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert cfg._config_home() == str(tmp_path / "config")


def test_get_data_dir_is_private_inside_flatpak(monkeypatch, tmp_path):
    cfg = _config()
    monkeypatch.setenv("FLATPAK_ID", "io.github.ronb1964.TalkType")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    # DATA_DIR is "TalkType" outside DEV_MODE.
    assert cfg.get_data_dir() == str(tmp_path / "data" / cfg.DATA_DIR)


def test_host_paths_ignore_xdg_and_stay_historical(monkeypatch, tmp_path):
    """On host (no FLATPAK_ID) the paths must remain ~/.config and ~/.local/share
    verbatim — even if XDG_*_HOME is set — so existing installs never move."""
    cfg = _config()
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdgcfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdgdata"))
    import os
    assert cfg._config_home() == os.path.expanduser("~/.config")
    assert cfg._data_home() == os.path.expanduser("~/.local/share")
    assert cfg.get_data_dir() == os.path.expanduser(f"~/.local/share/{cfg.DATA_DIR}")

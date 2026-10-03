"""OK in Preferences must close the window on Vulkan.

OK deliberately stays open after a model download, so the user can keep
adjusting. On Vulkan, _download_selected_model reported "downloaded" whenever
the files were merely present, so OK never closed Preferences for anyone on
Vulkan (0.12.0 to 0.13.1, found 2026-10-03).
"""
from types import SimpleNamespace

import pytest

from talktype import whisper_vulkan as wv


@pytest.fixture
def prefs_cls():
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "3.0")
    from talktype.prefs import PreferencesWindow
    return PreferencesWindow


def _stub(model, downloads):
    stub = SimpleNamespace(config={"model": model, "device": "vulkan"})
    stub._download_vulkan_files = lambda m, confirm: downloads.append(m) or True
    return stub


@pytest.mark.parametrize("model", ["small", "parakeet-v3"])
def test_files_already_there_are_not_reported_as_a_download(prefs_cls, monkeypatch, model):
    downloads = []
    monkeypatch.setattr(wv, "is_installed", lambda m: True)
    assert prefs_cls._download_selected_model(_stub(model, downloads)) == (True, False)


def test_a_real_download_is_reported(prefs_cls, monkeypatch):
    downloads = []
    monkeypatch.setattr(wv, "is_installed", lambda m: bool(downloads))
    assert prefs_cls._download_selected_model(_stub("parakeet-v3", downloads)) == (True, True)
    assert downloads == ["parakeet-v3"]

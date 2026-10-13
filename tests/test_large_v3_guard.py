"""large-v3 is only swapped for medium when it was meant to run on CUDA.

The guard predates Vulkan. It checked only for TalkType's CUDA libraries, so an
AMD or Intel user who set up large-v3 on their graphics card (Vulkan, 0.12.0)
silently got the medium model while the tray said "Large".
"""
import types

import pytest

from tuxtalk import app


def _cfg(device):
    return types.SimpleNamespace(model="large-v3", device=device)


@pytest.fixture
def no_cuda(monkeypatch):
    monkeypatch.setattr("tuxtalk.cuda_helper.has_cuda_libraries", lambda: False)
    monkeypatch.setattr(app, "_notify", lambda *a, **k: None)


def test_vulkan_keeps_large_v3(no_cuda):
    cfg = _cfg("vulkan")
    app._guard_large_v3_without_cuda(cfg)
    assert cfg.model == "large-v3"


@pytest.mark.parametrize("device", ["cuda", "cpu"])
def test_without_cuda_libraries_it_still_falls_back(no_cuda, device):
    cfg = _cfg(device)
    app._guard_large_v3_without_cuda(cfg)
    assert cfg.model == "medium"


def test_with_cuda_libraries_nothing_changes(monkeypatch):
    monkeypatch.setattr("tuxtalk.cuda_helper.has_cuda_libraries", lambda: True)
    cfg = _cfg("cuda")
    app._guard_large_v3_without_cuda(cfg)
    assert cfg.model == "large-v3"


def test_other_models_are_untouched(no_cuda):
    cfg = types.SimpleNamespace(model="parakeet-v3", device="cpu")
    app._guard_large_v3_without_cuda(cfg)
    assert cfg.model == "parakeet-v3"


def test_a_system_wide_cuda_install_keeps_large_v3(monkeypatch):
    """Preferences offers large-v3 when CUDA is installed system-wide (common
    on Arch). The guard checked only TuxTalk's own download, so those users
    silently got medium, and could be asked to download it."""
    monkeypatch.setattr("tuxtalk.cuda_helper.has_talktype_cuda_libraries", lambda: False)
    monkeypatch.setattr("tuxtalk.cuda_helper.has_cuda_libraries", lambda: True)
    cfg = _cfg("cuda")
    app._guard_large_v3_without_cuda(cfg)
    assert cfg.model == "large-v3"


def test_the_swap_is_told_to_the_user(monkeypatch):
    monkeypatch.setattr("tuxtalk.cuda_helper.has_cuda_libraries", lambda: False)
    notes = []
    monkeypatch.setattr(app, "_notify", lambda title, body: notes.append(body))
    app._guard_large_v3_without_cuda(_cfg("cuda"))
    assert notes and "Medium" in notes[0]
    # The CUDA download is offered in General, Device; Advanced only shows status.
    assert "General, Device" in notes[0]

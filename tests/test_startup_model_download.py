"""Starting the service when its speech model is not downloaded yet.

Two bugs found by clicking Cancel on the startup "Download model?" question:
Cancel was ignored on NVIDIA setups (it looked like a CUDA failure, and the
CUDA fallback re-downloaded without asking), and a startup download crashed
the service (its dialogs ran while Gtk.main() was live on another thread).
"""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from talktype import app, model_helper

ROOT = Path(__file__).resolve().parent.parent


def _settings(model="small", device="cuda"):
    return SimpleNamespace(model=model, device=device)


@pytest.fixture(autouse=True)
def cuda_installed(monkeypatch):
    """These tests are about downloads and load failures with CUDA present."""
    from talktype import cuda_helper
    monkeypatch.setattr(cuda_helper, "has_cuda_libraries", lambda: True)


def test_missing_cuda_files_use_the_processor_instead_of_crashing(monkeypatch):
    """Device CUDA with the CUDA files gone: the model still loads "on cuda",
    then the first dictation crashes the service inside the speech library
    (libcudnn_ops.so.9 not found), past every Python fallback. Ron, 0.14.5
    test. Use the processor for this run and say why; keep the setting."""
    from talktype import cuda_helper
    monkeypatch.setattr(cuda_helper, "has_cuda_libraries", lambda: False)
    loaded, notes = [], []
    monkeypatch.setattr(model_helper, "download_model_with_progress",
                        lambda *a, **k: loaded.append(k.get("device")) or object())
    monkeypatch.setattr(app, "_notify", lambda *a: notes.append(a))
    settings = _settings(device="cuda")
    app.build_model(settings)
    assert loaded == ["cpu"]
    assert settings.device == "cuda"          # the user's choice is kept
    assert notes and "CUDA" in notes[0][1]


def test_cancel_is_respected_on_an_nvidia_setup(monkeypatch):
    calls = []
    monkeypatch.setattr(model_helper, "download_model_with_progress",
                        lambda *a, **k: calls.append(k) or None)
    with pytest.raises(app.ModelUnavailable):
        app.build_model(_settings(device="cuda"))
    assert len(calls) == 1   # asked once; no silent CPU retry


def test_cancel_stops_the_service_when_no_other_model_is_downloaded(monkeypatch):
    monkeypatch.setattr(model_helper, "download_model_with_progress", lambda *a, **k: None)
    monkeypatch.setattr(model_helper, "is_model_cached_fast", lambda m: False)
    with pytest.raises(SystemExit):
        app._build_model_or_exit(_settings())


def test_parakeet_never_takes_the_cuda_fallback(monkeypatch):
    calls = []

    def fail(*a, **k):
        calls.append(k)
        raise RuntimeError("load failed")

    monkeypatch.setattr(model_helper, "download_model_with_progress", fail)
    with pytest.raises(RuntimeError):
        app.build_model(_settings(model="parakeet-v3", device="cuda"))
    assert len(calls) == 1


def test_a_real_cuda_failure_still_falls_back_to_cpu(monkeypatch):
    calls = []

    def load(*a, **k):
        calls.append(k.get("device"))
        if k.get("device") == "cuda":
            raise RuntimeError("CUDA driver missing")
        return object()

    monkeypatch.setattr(model_helper, "download_model_with_progress", load)
    monkeypatch.setattr("talktype.config.save_config", lambda cfg: None)
    assert app.build_model(_settings(device="cuda")) is not None
    assert calls == ["cuda", "cpu"]


def test_a_needed_download_happens_before_the_gtk_thread_starts():
    """Only one thread may drive GTK: the download dialogs must run before
    Gtk.main() starts on its background thread."""
    main_src = (ROOT / "src/talktype/app.py").read_text().split("\ndef main():", 1)[1]
    early_build = main_src.index("if not is_model_cached_fast(cfg.model):")
    thread_start = main_src.index("gtk_thread.start()")
    assert early_build < thread_start


@pytest.mark.parametrize("wanted,downloaded,cuda,expected", [
    ("parakeet-v3", ["small", "large-v3"], True, "large-v3"),   # nearest in quality
    ("parakeet-v3", ["small", "large-v3"], False, "small"),     # large-v3 needs CUDA
    ("parakeet-v3", ["medium", "large-v3"], True, "medium"),    # tie -> the faster one
    ("base", ["tiny", "small"], False, "tiny"),                 # tie -> the faster one
    ("small", ["tiny", "medium"], False, "medium"),             # medium is one step away, tiny two
    ("medium", [], False, None),                                # nothing to fall back to
    ("tiny", ["tiny"], False, None),                            # never "falls back" to itself
])
def test_fallback_picks_the_nearest_downloaded_model(wanted, downloaded, cuda, expected):
    assert app._pick_fallback_model(wanted, downloaded, cuda) == expected


def test_cancel_falls_back_to_a_downloaded_model_and_saves_it(monkeypatch):
    import talktype.config as config
    from talktype import cuda_helper

    def download(name, **k):
        return None if name == "parakeet-v3" else f"model:{name}"

    saved, notes = [], []
    monkeypatch.setattr(model_helper, "download_model_with_progress", download)
    monkeypatch.setattr(model_helper, "is_model_cached_fast", lambda m: m in ("small", "large-v3"))
    monkeypatch.setattr(cuda_helper, "has_talktype_cuda_libraries", lambda: False)
    monkeypatch.setattr(config, "load_config", lambda: SimpleNamespace(model="parakeet-v3"))
    monkeypatch.setattr(config, "save_config", lambda cfg: saved.append(cfg.model))
    monkeypatch.setattr(app, "_notify", lambda title, body: notes.append(body))

    settings = _settings(model="parakeet-v3", device="cpu")
    assert app._build_model_or_exit(settings) == "model:small"
    assert settings.model == "small" and saved == ["small"]
    assert "Parakeet wasn't downloaded" in notes[0] and "Small" in notes[0]

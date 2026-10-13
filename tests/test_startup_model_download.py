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

from tuxtalk import app, model_helper

ROOT = Path(__file__).resolve().parent.parent


def _settings(model="small", device="cuda"):
    return SimpleNamespace(model=model, device=device)


@pytest.fixture(autouse=True)
def cuda_installed(monkeypatch):
    """These tests are about downloads and load failures with CUDA present."""
    from tuxtalk import cuda_helper
    monkeypatch.setattr(cuda_helper, "has_cuda_libraries", lambda: True)


def test_missing_cuda_files_use_the_processor_instead_of_crashing(monkeypatch):
    """Device CUDA with the CUDA files gone: the model still loads "on cuda",
    then the first dictation crashes the service inside the speech library
    (libcudnn_ops.so.9 not found), past every Python fallback. Ron, 0.14.5
    test. Use the processor for this run and say why; keep the setting."""
    from tuxtalk import cuda_helper
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
    assert "General, Device" in notes[0][1]   # where the CUDA download is offered


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
    monkeypatch.setattr("tuxtalk.config.save_config", lambda cfg: None)
    assert app.build_model(_settings(device="cuda")) is not None
    assert calls == ["cuda", "cpu"]


def test_a_needed_download_happens_before_the_gtk_thread_starts():
    """Only one thread may drive GTK: the download dialogs must run before
    Gtk.main() starts on its background thread."""
    main_src = (ROOT / "src/tuxtalk/app.py").read_text().split("\ndef main():", 1)[1]
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
    import tuxtalk.config as config
    from tuxtalk import cuda_helper

    def download(name, **k):
        return None if name == "parakeet-v3" else f"model:{name}"

    saved, notes = [], []
    monkeypatch.setattr(model_helper, "download_model_with_progress", download)
    monkeypatch.setattr(model_helper, "is_model_cached_fast", lambda m: m in ("small", "large-v3"))
    monkeypatch.setattr(cuda_helper, "has_cuda_libraries", lambda: False)
    monkeypatch.setattr(config, "load_config", lambda: SimpleNamespace(model="parakeet-v3"))
    monkeypatch.setattr(config, "save_config", lambda cfg: saved.append(cfg.model))
    monkeypatch.setattr(app, "_notify", lambda title, body: notes.append(body))

    settings = _settings(model="parakeet-v3", device="cpu")
    assert app._build_model_or_exit(settings) == "model:small"
    assert settings.model == "small" and saved == ["small"]
    assert "Parakeet wasn't downloaded" in notes[0] and "Small" in notes[0]


def test_a_cancelled_cpu_retry_is_a_missing_model_not_a_crash(monkeypatch):
    """CUDA failed, then the processor copy was cancelled. A bare Exception
    escaped _build_model_or_exit (which handles ModelUnavailable) and crashed
    the service with a traceback instead of using a downloaded model."""
    def load(*a, **k):
        if k.get("device") == "cuda":
            raise RuntimeError("CUDA driver missing")
        return None

    monkeypatch.setattr(model_helper, "download_model_with_progress", load)
    with pytest.raises(app.ModelUnavailable):
        app.build_model(_settings(device="cuda"))


def test_a_model_load_error_is_not_reported_as_a_gtk_failure():
    """The early build sat inside the GTK setup's try: a load error was logged
    as "GTK initialization failed", the GTK loop never started, and the model
    was then built a second time."""
    main_src = (ROOT / "src/tuxtalk/app.py").read_text().split("\ndef main():", 1)[1]
    gtk_except = main_src.index('logger.error(f"GTK initialization failed')
    early_build = main_src.index("if not is_model_cached_fast(cfg.model):")
    assert gtk_except < early_build


def test_broken_files_raise_instead_of_opening_dialogs_off_the_gtk_thread(monkeypatch):
    """With Gtk.main() on another thread, the service's main thread must not
    run the download dialogs for a model whose files won't load."""
    def broken(*a, **k):
        raise RuntimeError("bad model.bin")

    def no_dialogs(*a, **k):
        raise AssertionError("a GTK dialog was opened")

    monkeypatch.setattr(model_helper, "is_model_cached_fast", lambda m: True)
    monkeypatch.setattr(model_helper, "load_model", broken)
    monkeypatch.setattr(model_helper, "_loads_on_cpu", lambda m: False)
    monkeypatch.setattr(model_helper, "message_dialog", no_dialogs)
    monkeypatch.setattr(model_helper.Gtk, "Dialog", no_dialogs)
    with pytest.raises(model_helper.BrokenModelFiles):
        model_helper.download_model_with_progress("small", redownload_broken=False)


def test_the_service_treats_broken_files_as_an_unavailable_model(monkeypatch):
    asked = []

    def broken(*a, **k):
        asked.append(k.get("redownload_broken"))
        raise model_helper.BrokenModelFiles("small won't load")

    monkeypatch.setattr(app, "_gtk_loop_running", True)
    monkeypatch.setattr(model_helper, "download_model_with_progress", broken)
    with pytest.raises(app.ModelUnavailable):
        app.build_model(_settings(device="cpu"))
    assert asked == [False]


def test_a_model_that_wont_load_falls_back_without_replacing_the_choice(monkeypatch):
    """Downloaded files that won't load were reported as "wasn't downloaded"
    and the fallback was saved, so the chosen model was replaced at every
    start: choosing it again in Preferences downloads nothing."""
    import tuxtalk.config as config
    from tuxtalk import cuda_helper

    def load(name, **k):
        if name == "medium":
            raise model_helper.BrokenModelFiles("medium won't load")
        return f"model:{name}"

    saved, notes = [], []
    monkeypatch.setattr(model_helper, "download_model_with_progress", load)
    monkeypatch.setattr(model_helper, "is_model_cached_fast", lambda m: m in ("small", "medium"))
    monkeypatch.setattr(cuda_helper, "has_cuda_libraries", lambda: False)
    monkeypatch.setattr(config, "save_config", lambda cfg: saved.append(cfg.model))
    monkeypatch.setattr(app, "_notify", lambda title, body: notes.append(body))

    settings = _settings(model="medium", device="cpu")
    assert app._build_model_or_exit(settings) == "model:small"
    assert settings.model == "small" and saved == []
    assert "wouldn't load" in notes[0] and "wasn't downloaded" not in notes[0]

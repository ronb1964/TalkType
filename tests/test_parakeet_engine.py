"""Parakeet engine wiring.

Parakeet is offered as one more model name ("parakeet-v3") so that every model
picker, the config validator and the download dialogs handle it without their
own special cases. These tests pin down the places where it genuinely differs
from Whisper: which files are downloaded, how "is it downloaded?" is answered,
and how dictation audio reaches it.
"""
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def test_parakeet_is_offered_valid_and_downloadable():
    from talktype.config import VALID_MODELS
    from talktype.model_helper import MODEL_REPOS, MODEL_DISPLAY_SIZES, OFFERED_MODELS
    from talktype.parakeet_engine import PARAKEET_MODEL

    assert PARAKEET_MODEL in OFFERED_MODELS
    assert PARAKEET_MODEL in VALID_MODELS
    assert PARAKEET_MODEL in MODEL_REPOS
    assert PARAKEET_MODEL in MODEL_DISPLAY_SIZES


def test_every_offered_model_has_a_label_on_every_picker():
    """Both pickers index a label dict by model id; a missing key crashes the
    screen as it opens, which on the setup screen means no way to finish setup."""
    from talktype.model_helper import OFFERED_MODELS

    for path, dict_name in (("src/talktype/prefs.py", "_MODEL_DISPLAY"),
                            ("src/talktype/welcome_dialog.py", "_MODEL_LABELS")):
        source = (ROOT / path).read_text()
        body = re.search(dict_name + r" = \{(.*?)\n\s*\}", source, re.S).group(1)
        keys = set(re.findall(r'"([^"]+)":', body))
        missing = set(OFFERED_MODELS) - keys
        assert not missing, f"{path} {dict_name} has no label for {sorted(missing)}"


def test_only_the_int8_files_are_downloaded(monkeypatch):
    """The repo also holds a 2.4 GB full-precision copy that must never be fetched."""
    import huggingface_hub
    from talktype import model_helper
    from talktype.parakeet_engine import PARAKEET_FILES, PARAKEET_MODEL, PARAKEET_REPO

    repo_files = [
        (".gitattributes", 1579), ("README.md", 1207), ("config.json", 97),
        ("decoder_joint-model.int8.onnx", 18202004),
        ("decoder_joint-model.onnx", 72520893),
        ("encoder-model.int8.onnx", 652183999),
        ("encoder-model.onnx", 41770866),
        ("encoder-model.onnx.data", 2435420160),
        ("nemo128.onnx", 139764), ("vocab.txt", 93939),
    ]
    monkeypatch.setattr(
        huggingface_hub, "list_repo_tree",
        lambda repo_id, recursive=True: [SimpleNamespace(path=p, size=s) for p, s in repo_files],
    )

    files = model_helper._files_to_download(PARAKEET_MODEL, PARAKEET_REPO)

    assert {p for p, _ in files} == set(PARAKEET_FILES)
    assert sum(s for _, s in files) < 700 * 1024 * 1024


def test_whisper_downloads_are_not_filtered(monkeypatch):
    import huggingface_hub
    from talktype import model_helper

    monkeypatch.setattr(
        huggingface_hub, "list_repo_tree",
        lambda repo_id, recursive=True: [SimpleNamespace(path="model.bin", size=10),
                                         SimpleNamespace(path="README.md", size=1)],
    )
    files = model_helper._files_to_download("small", "Systran/faster-whisper-small")
    assert {p for p, _ in files} == {"model.bin", "README.md"}


def test_cache_checks_use_parakeet_files(monkeypatch):
    from talktype import model_helper

    monkeypatch.setattr(model_helper, "_parakeet_cached_dir", lambda: None)
    assert model_helper.is_model_cached_fast("parakeet-v3") is False
    assert model_helper.is_model_cached("parakeet-v3") is False

    monkeypatch.setattr(model_helper, "_parakeet_cached_dir", lambda: "/some/dir")
    assert model_helper.is_model_cached_fast("parakeet-v3") is True
    assert model_helper.is_model_cached("parakeet-v3") is True


def test_missing_parakeet_file_makes_the_download_unusable():
    from talktype import model_helper

    assert model_helper._download_is_usable(["README.md"], "parakeet-v3")
    assert not model_helper._download_is_usable(["encoder-model.int8.onnx"], "parakeet-v3")


def test_dictation_audio_goes_to_parakeet(monkeypatch):
    from talktype import app
    from talktype.parakeet_engine import ParakeetModel

    received = []
    fake = ParakeetModel.__new__(ParakeetModel)  # skip loading the real model
    fake.recognize = lambda audio: received.append(audio) or "Hello there."
    monkeypatch.setattr(app, "model", fake, raising=False)

    audio = np.zeros(16000, dtype=np.float32)
    assert app._transcribe_audio(audio, language="de") == "Hello there."
    assert received and received[0] is audio


def test_parakeet_silence_returns_none(monkeypatch):
    from talktype import app
    from talktype.parakeet_engine import ParakeetModel

    fake = ParakeetModel.__new__(ParakeetModel)
    fake.recognize = lambda audio: ""
    monkeypatch.setattr(app, "model", fake, raising=False)

    assert app._transcribe_audio(np.zeros(8000, dtype=np.float32), language=None) is None


def test_display_name_is_friendly():
    from talktype.model_helper import model_display_name
    assert model_display_name("parakeet-v3") == "Parakeet"
    assert model_display_name("small") == "Small"

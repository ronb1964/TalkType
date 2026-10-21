"""A model download must fail on missing weights, not on a missing README.

The downloader walks every file in the HuggingFace repo — including
.gitattributes, README.md and other files faster-whisper never loads — so
treating any single failure as total failure would let a flaky fetch of a text
file throw away a completed multi-gigabyte model download.

What faster-whisper actually needs is already spelled out in this module:
model.bin, config.json, tokenizer.json.
"""

from tuxtalk.model_helper import ESSENTIAL_MODEL_FILES, _download_is_usable


def test_a_missing_readme_does_not_fail_the_download():
    assert _download_is_usable(["README.md"]) is True


def test_a_missing_gitattributes_does_not_fail_the_download():
    assert _download_is_usable([".gitattributes", "README.md"]) is True


def test_a_missing_model_binary_fails():
    assert _download_is_usable(["model.bin"]) is False


def test_a_missing_config_fails():
    assert _download_is_usable(["config.json"]) is False


def test_a_missing_tokenizer_fails():
    assert _download_is_usable(["tokenizer.json"]) is False


def test_nothing_failed_is_usable():
    assert _download_is_usable([]) is True


def test_an_essential_file_in_a_subdirectory_still_counts():
    """list_repo_tree is recursive, so paths can be nested."""
    assert _download_is_usable(["snapshots/abc/model.bin"]) is False


def test_the_essential_list_matches_what_the_cache_check_requires():
    """Both places must agree on what a usable model is."""
    assert set(ESSENTIAL_MODEL_FILES) == {"model.bin", "config.json", "tokenizer.json"}


def test_a_missing_vocabulary_fails():
    """ctranslate2 can't load a Whisper model without it (.txt or .json)."""
    assert _download_is_usable(["vocabulary.json"]) is False
    assert _download_is_usable(["vocabulary.txt"]) is False


def test_a_file_asked_for_by_name_is_never_optional(monkeypatch):
    """The AI model is fetched as one named file, which isn't on the Whisper
    list; a failed download of it must still count as a failure."""
    import huggingface_hub
    from tuxtalk import model_helper as M

    def fails(**kwargs):
        raise OSError("connection reset")
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fails)
    monkeypatch.setattr(M, "_files_to_download", lambda repo: [("model.gguf", 10)])
    download = M.make_model_download_func("AI model", repo_id="some/repo",
                                          only_files=["model.gguf"])
    assert download(lambda *a: None, type("E", (), {"is_set": lambda self: False})()) is False


def test_the_disk_space_check_looks_where_the_files_go(monkeypatch):
    """HF_HOME / XDG_CACHE_HOME (the Flatpak sets the latter) move the cache;
    measuring ~/.cache/huggingface would check the wrong disk."""
    import huggingface_hub.constants
    from tuxtalk import download_utils
    from tuxtalk import model_helper as M

    asked = []
    monkeypatch.setattr(huggingface_hub.constants, "HF_HUB_CACHE", "/elsewhere/hub")
    monkeypatch.setattr(download_utils, "free_space_bytes",
                        lambda path: asked.append(path) or 1)
    monkeypatch.setattr(M, "_files_to_download", lambda repo: [("model.bin", 10 ** 9)])
    messages = []
    download = M.make_model_download_func("small")
    assert download(lambda msg, pct: messages.append(msg),
                    type("E", (), {"is_set": lambda self: False})()) is False
    assert asked == ["/elsewhere/hub"]
    assert "Not enough disk space" in messages[-1]

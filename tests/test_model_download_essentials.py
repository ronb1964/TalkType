"""A model download must fail on missing weights, not on a missing README.

The downloader walks every file in the HuggingFace repo — including
.gitattributes, README.md and other files faster-whisper never loads — and
treated any single failure as total failure. A flaky fetch of a text file
therefore threw away a completed multi-gigabyte model download and told the
user it had failed.

What faster-whisper actually needs is already spelled out in this module:
model.bin, config.json, tokenizer.json.
"""

from talktype.model_helper import ESSENTIAL_MODEL_FILES, _download_is_usable


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
    list, so a failed download of it used to count as a success."""
    import huggingface_hub
    from talktype import model_helper as M

    def fails(**kwargs):
        raise OSError("connection reset")
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fails)
    monkeypatch.setattr(M, "_files_to_download", lambda name, repo: [("model.gguf", 10)])
    download = M.make_model_download_func("AI model", repo_id="some/repo",
                                          only_files=["model.gguf"])
    assert download(lambda *a: None, type("E", (), {"is_set": lambda self: False})()) is False

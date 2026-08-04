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

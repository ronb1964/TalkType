"""A slow moment must not sink a whole model download.

Two first runs in the VM tests (2026-10-13) lost Parakeet to one read timeout:
the file wasn't retried, the log still said "All files downloaded", and
setup quietly fell back to Whisper Small.
"""
import pytest

from tuxtalk import model_helper as mh


def test_a_file_that_fails_once_is_fetched_again():
    calls = []

    def fetch():
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError("The read operation timed out")
        return "/path"

    assert mh._fetch_with_retry(fetch, "vocab.txt", sleep=lambda s: None) == "/path"
    assert len(calls) == 2


def test_it_gives_up_after_three_tries_with_the_last_error():
    calls = []

    def fetch():
        calls.append(1)
        raise TimeoutError(f"try {len(calls)}")

    with pytest.raises(TimeoutError, match="try 3"):
        mh._fetch_with_retry(fetch, "vocab.txt", sleep=lambda s: None)
    assert len(calls) == 3


def test_a_cancel_is_never_retried():
    calls = []

    def fetch():
        calls.append(1)
        raise InterruptedError("Download cancelled")

    with pytest.raises(InterruptedError):
        mh._fetch_with_retry(fetch, "vocab.txt", sleep=lambda s: None)
    assert len(calls) == 1


def test_waits_grow_between_tries():
    waits = []

    def fetch():
        raise OSError("network")

    with pytest.raises(OSError):
        mh._fetch_with_retry(fetch, "x", sleep=waits.append)
    assert waits == sorted(waits) and len(waits) == 2 and waits[0] > 0

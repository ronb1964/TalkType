"""Tests for the shared download helper (uses file:// URLs — no network)."""
import hashlib
import os
import threading

from tuxtalk.download_utils import (
    download_file,
    parse_sha256sums,
    free_space_bytes,
)


def _make_source(tmp_path, content=b"hello talktype" * 1000):
    src = tmp_path / "source.bin"
    src.write_bytes(content)
    return src, content


def test_download_file_success(tmp_path):
    src, content = _make_source(tmp_path)
    dest = tmp_path / "out" / "dest.bin"
    assert download_file(src.as_uri(), str(dest)) is True
    assert dest.read_bytes() == content
    assert not os.path.exists(str(dest) + ".tmp")


def test_download_file_sha256_match(tmp_path):
    src, content = _make_source(tmp_path)
    dest = tmp_path / "dest.bin"
    good = hashlib.sha256(content).hexdigest()
    assert download_file(src.as_uri(), str(dest), expected_sha256=good.upper()) is True
    assert dest.exists()


def test_download_file_sha256_mismatch_rejects(tmp_path):
    """A corrupted/tampered download must never land at the destination."""
    src, _ = _make_source(tmp_path)
    dest = tmp_path / "dest.bin"
    assert download_file(src.as_uri(), str(dest), expected_sha256="0" * 64) is False
    assert not dest.exists()
    assert not os.path.exists(str(dest) + ".tmp")


def test_download_file_cancelled(tmp_path):
    src, _ = _make_source(tmp_path)
    dest = tmp_path / "dest.bin"
    cancel = threading.Event()
    cancel.set()
    assert download_file(src.as_uri(), str(dest), cancel_event=cancel) is False
    assert not dest.exists()


def test_download_file_progress_hook(tmp_path):
    src, content = _make_source(tmp_path)
    dest = tmp_path / "dest.bin"
    seen = []
    assert download_file(src.as_uri(), str(dest),
                         progress_hook=lambda done, total: seen.append((done, total))) is True
    assert seen, "progress hook never called"
    assert seen[-1][0] == len(content)


def test_download_file_bad_url(tmp_path):
    dest = tmp_path / "dest.bin"
    assert download_file((tmp_path / "missing.bin").as_uri(), str(dest)) is False
    assert not dest.exists()


def test_parse_sha256sums():
    text = (
        "abc123  TalkType-v0.5.17-x86_64.AppImage\n"
        "def456 *talktype-gnome-extension.zip\n"
        "\n"
        "# a comment line is ignored\n"
    )
    sums = parse_sha256sums(text)
    assert sums["TalkType-v0.5.17-x86_64.AppImage"] == "abc123"
    assert sums["talktype-gnome-extension.zip"] == "def456"
    assert len(sums) == 2


def test_free_space_bytes(tmp_path):
    # Must return a positive number for an existing dir and not raise for
    # a not-yet-created subdirectory (checks the nearest existing parent).
    assert free_space_bytes(str(tmp_path)) > 0
    assert free_space_bytes(str(tmp_path / "not" / "yet" / "created")) > 0


def test_each_download_has_its_own_temp_file(tmp_path):
    """Two downloads of one file at once must not share a temp file: one could
    overwrite the bytes the other already hash-checked."""
    src, content = _make_source(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    dest = out / "dest.bin"
    others = out / "dest.bin.tmp"
    others.write_bytes(b"another download in progress")

    assert download_file(src.as_uri(), str(dest)) is True

    assert dest.read_bytes() == content
    assert others.read_bytes() == b"another download in progress"
    assert sorted(p.name for p in out.iterdir()) == ["dest.bin", "dest.bin.tmp"]
    assert (dest.stat().st_mode & 0o777) == 0o644


def test_a_failed_download_leaves_no_temp_file(tmp_path):
    src, _ = _make_source(tmp_path)
    out = tmp_path / "out"
    assert download_file(src.as_uri(), str(out / "dest.bin"), expected_sha256="0" * 64) is False
    assert list(out.iterdir()) == []

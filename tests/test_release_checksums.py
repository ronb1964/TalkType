"""replace_checksums (packaging/checksums.sh) swaps one file's lines in
SHA256SUMS.txt and keeps every other line, above all the AppImage's, which
the in-app updater verifies against."""
import hashlib
import os
import pathlib
import subprocess

import pytest

HELPER = pathlib.Path(__file__).resolve().parent.parent / "packaging" / "checksums.sh"
APPIMAGE_LINE = "a" * 64 + "  TuxTalk-v0.15.0-x86_64.AppImage\n"


def _run(folder, *names):
    return subprocess.run(
        ["bash", "-c", 'source "$0"; replace_checksums "$@"', str(HELPER), str(folder), *names],
        capture_output=True, text=True)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_replaces_the_old_line_and_keeps_the_others(tmp_path):
    deb = tmp_path / "tuxtalk_0.15.0_amd64.deb"
    deb.write_bytes(b"new package")
    # An old line for the deb, and one whose name only differs at the dot,
    # which a regex match on the name would also have dropped.
    sums = tmp_path / "SHA256SUMS.txt"
    sums.write_text(APPIMAGE_LINE
                    + "b" * 64 + "  tuxtalk_0.15.0_amd64.deb\n"
                    + "c" * 64 + "  tuxtalk_0.15.0_amd64Xdeb\n")
    assert _run(tmp_path, deb.name).returncode == 0
    assert sums.read_text() == (APPIMAGE_LINE
                                + "c" * 64 + "  tuxtalk_0.15.0_amd64Xdeb\n"
                                + f"{_sha(deb)}  {deb.name}\n")


def test_several_files_and_no_existing_sums(tmp_path):
    for name in ("tuxtalk-gnome-extension.zip", "talktype-gnome-extension.zip"):
        (tmp_path / name).write_bytes(b"zip")
    assert _run(tmp_path, "tuxtalk-gnome-extension.zip", "talktype-gnome-extension.zip").returncode == 0
    lines = (tmp_path / "SHA256SUMS.txt").read_text().splitlines()
    assert [line.split()[1] for line in lines] == ["tuxtalk-gnome-extension.zip",
                                                   "talktype-gnome-extension.zip"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read the file anyway")
def test_an_unreadable_file_is_left_untouched(tmp_path):
    (tmp_path / "x.rpm").write_bytes(b"rpm")
    sums = tmp_path / "SHA256SUMS.txt"
    sums.write_text(APPIMAGE_LINE)
    sums.chmod(0)
    try:
        result = _run(tmp_path, "x.rpm")
    finally:
        sums.chmod(0o644)
    assert result.returncode != 0
    assert sums.read_text() == APPIMAGE_LINE
    assert not (tmp_path / "SHA256SUMS.txt.tmp").exists()

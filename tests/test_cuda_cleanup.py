"""A failed CUDA re-download must not delete the CUDA the user already has.

download_cuda_libraries() cleans up on failure by rmtree'ing the whole CUDA
directory. That is right when the directory is a half-finished download this
run created. It is wrong when a complete 1.4 GB installation was already
there: an early failure — no network, pip missing, a cancelled dialog —
then destroyed a working GPU setup the user has to spend 1.4 GB re-fetching.
"""

import os

import pytest

from talktype import cuda_helper


@pytest.fixture
def cuda_dir(tmp_path, monkeypatch):
    path = tmp_path / "cuda"
    monkeypatch.setattr(cuda_helper, "get_appdir_cuda_path", lambda: str(path))
    return path


def _install_complete_cuda(path):
    """Look like a real, complete CUDA install."""
    lib = path / "lib"
    lib.mkdir(parents=True)
    for name in ("libcudart.so", "libcublas.so", "libcudnn.so"):
        (lib / name).write_text("x" * 1000)
    return sorted(os.listdir(lib))


def test_a_pre_existing_install_survives_a_failed_download(cuda_dir):
    before = _install_complete_cuda(cuda_dir)

    cleanup = cuda_helper._make_cuda_cleanup(str(cuda_dir))
    cleanup()

    assert cuda_dir.exists(), "deleted the user's working CUDA installation"
    assert sorted(os.listdir(cuda_dir / "lib")) == before


def test_a_partial_download_is_cleaned_up(cuda_dir):
    """Nothing usable was there before, so removing the debris is correct."""
    lib = cuda_dir / "lib"
    lib.mkdir(parents=True)
    (lib / "libcudart.so.partial").write_text("half a file")

    cleanup = cuda_helper._make_cuda_cleanup(str(cuda_dir))
    cleanup()

    assert not cuda_dir.exists(), "left a broken half-download in place"

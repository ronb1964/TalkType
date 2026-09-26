"""The AppImage's bundled PortAudio is used only when the system has none.

sounddevice finds PortAudio with ctypes.util.find_library("portaudio"), which
consults the system's linker cache and ignores the AppImage's library folder.
AppImageHub's test machine has no libportaudio, so TalkType showed its
"PortAudio library not found" dialog there (2026-09-26).
"""

import ctypes.util

import pytest

import talktype


@pytest.fixture(autouse=True)
def restore_find_library(monkeypatch):
    # Every test patches through monkeypatch so the real function comes back.
    monkeypatch.setattr(ctypes.util, "find_library", ctypes.util.find_library)


def _bundle(tmp_path):
    lib_dir = tmp_path / "portaudio"
    lib_dir.mkdir()
    (lib_dir / "libportaudio.so.2").write_bytes(b"")
    return lib_dir


def test_falls_back_to_bundled_copy_when_system_has_none(tmp_path, monkeypatch):
    monkeypatch.setattr(ctypes.util, "find_library", lambda name: None)
    lib_dir = _bundle(tmp_path)

    talktype._use_bundled_portaudio(str(lib_dir))

    assert ctypes.util.find_library("portaudio") == str(lib_dir / "libportaudio.so.2")


def test_system_portaudio_still_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(ctypes.util, "find_library", lambda name: "libportaudio.so.2")
    lib_dir = _bundle(tmp_path)

    talktype._use_bundled_portaudio(str(lib_dir))

    assert ctypes.util.find_library("portaudio") == "libportaudio.so.2"


def test_other_libraries_are_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(ctypes.util, "find_library", lambda name: None)
    talktype._use_bundled_portaudio(str(_bundle(tmp_path)))

    assert ctypes.util.find_library("asound") is None


def test_no_bundle_means_no_change(tmp_path, monkeypatch):
    original = lambda name: None
    monkeypatch.setattr(ctypes.util, "find_library", original)

    talktype._use_bundled_portaudio(str(tmp_path / "missing"))

    assert ctypes.util.find_library is original

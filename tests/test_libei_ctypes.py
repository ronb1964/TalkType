"""Pure-logic checks for the libei ctypes wrapper. The actual keystroke
injection needs a live EIS connection and is exercised by the Flatpak
integration test (BB-9), not here."""
import ctypes

import pytest

from talktype import libei_ctypes as L


def test_keycode_map_covers_punctuated_output():
    for ch in "Hello, world! 123?":
        assert ch in L.CHAR_TO_KEYCODE, f"missing keycode for {ch!r}"
    assert L.CHAR_TO_KEYCODE["h"] == 35
    assert L.CHAR_TO_KEYCODE[","] == 51


def test_uppercase_and_shifted_need_shift():
    # 'H' shares 'h' keycode but needs Shift; '?' shares '/' keycode + Shift.
    assert L.CHAR_TO_KEYCODE["H"] == L.CHAR_TO_KEYCODE["h"]
    assert "H" in L.SHIFT_CHARS
    assert "?" in L.SHIFT_CHARS
    assert "h" not in L.SHIFT_CHARS


def test_enum_constants():
    assert L.EI_EVENT_SEAT_ADDED == 3
    assert L.EI_EVENT_DEVICE_RESUMED == 8
    assert L.EI_DEVICE_CAP_KEYBOARD == 4


def test_load_libei_sets_signatures_or_skips():
    try:
        ei = L.load_libei()
    except OSError:
        pytest.skip("libei.so.1 not present on this host")
    assert ei.ei_new_sender.restype == ctypes.c_void_p
    assert ei.ei_setup_backend_fd.restype == ctypes.c_int

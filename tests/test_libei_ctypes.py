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


class _FakeEi:
    """Records the (keycode, pressed) sequence emitted through libei, so the key
    combos can be asserted without a live EIS connection."""

    def __init__(self):
        self.events = []

    def ei_device_keyboard_key(self, dev, keycode, pressed):
        self.events.append((keycode, bool(pressed)))

    def ei_device_frame(self, dev, when):
        pass

    def ei_now(self, ctx):
        return 0

    def ei_device_start_emulating(self, dev, seq):
        pass

    def ei_device_stop_emulating(self, dev):
        pass

    def ei_dispatch(self, ctx):
        pass

    def ei_get_event(self, ctx):
        return None  # nothing queued -> _drain loop exits immediately


def _fake_ready_session(monkeypatch):
    """A LibeiSession with a fake ei and a live device, bypassing __init__ (which
    needs a real EIS fd). time.sleep is neutralised so the flush loop is instant."""
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)
    s = L.LibeiSession.__new__(L.LibeiSession)
    s.ei = _FakeEi()
    s.ctx = object()
    s.device = object()
    s._seq = 0
    return s


def test_libei_select_all_delete_emits_ctrl_a_then_backspace(monkeypatch):
    s = _fake_ready_session(monkeypatch)
    assert s.select_all_delete() is True
    assert s.ei.events == [
        (L.KEY_LEFTCTRL, True),
        (L.KEY_A, True),
        (L.KEY_A, False),
        (L.KEY_LEFTCTRL, False),
        (L.KEY_BACKSPACE, True),
        (L.KEY_BACKSPACE, False),
    ]


def test_libei_backspaces_emits_n_backspaces(monkeypatch):
    s = _fake_ready_session(monkeypatch)
    assert s.backspaces(3) is True
    assert s.ei.events == [
        (L.KEY_BACKSPACE, True), (L.KEY_BACKSPACE, False),
        (L.KEY_BACKSPACE, True), (L.KEY_BACKSPACE, False),
        (L.KEY_BACKSPACE, True), (L.KEY_BACKSPACE, False),
    ]


def test_libei_backspaces_zero_is_noop(monkeypatch):
    s = _fake_ready_session(monkeypatch)
    assert s.backspaces(0) is True
    assert s.ei.events == []

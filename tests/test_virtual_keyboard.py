"""TuxTalk's own virtual keyboard (virtual_keyboard.py).

Every test here runs on the recording keyboard from conftest.py; a real one
would type into whatever window has the focus on the computer running them.
"""
import pytest

from tuxtalk import app, virtual_keyboard


def test_a_short_dictation_types_in_a_fraction_of_the_time_ydotool_took(keyboard):
    """ydotool needed about 0.6 s for 25 characters (24 ms a letter, VM
    measurement 2026-10-20); typing is the slowest step anyone sees."""
    assert app._type_text_raw("see you at noon tomorrow.") is True
    assert keyboard.clock.now < 0.15


def test_a_long_dictation_is_typed_to_the_end(keyboard):
    """ydotool's time limit cut long dictations off partway; nothing here may."""
    text = "word " * 400
    assert app._type_text_raw(text) is True
    assert keyboard.typed_keys().count(57) == 400      # every space


def test_the_typing_delay_setting_slows_every_key(keyboard, monkeypatch):
    monkeypatch.setattr(app, "_typing_delay", 20)
    app._type_text_raw("abcde")
    assert keyboard.clock.now == pytest.approx(10 * 0.020)


def test_keys_wait_until_the_desktop_has_taken_on_a_new_keyboard(keyboard, monkeypatch):
    """Keys sent the moment the keyboard appears are lost (the first letters
    of the dictation were missing in the VMs)."""
    monkeypatch.setattr(virtual_keyboard, "_ready_at", virtual_keyboard.SETTLE_S)
    seen_at = []
    write = keyboard.write
    monkeypatch.setattr(keyboard, "write", lambda *a: seen_at.append(keyboard.clock.now) or write(*a))
    virtual_keyboard.send([(30, 1), (30, 0)])
    assert seen_at[0] >= virtual_keyboard.SETTLE_S


def test_a_keyboard_that_fails_before_any_key_reports_nothing_sent(keyboard):
    keyboard.fail_after = 0
    assert app._send_backspaces(5) is False


def test_a_keyboard_that_fails_partway_says_so(keyboard):
    """Undo must know some backspaces landed: its buffer no longer matches."""
    keyboard.fail_after = 3
    with pytest.raises(virtual_keyboard.StoppedPartway):
        app._send_backspaces(5)


def test_a_keyboard_that_failed_is_made_again_next_time(keyboard, monkeypatch):
    keyboard.fail_after = 1
    with pytest.raises(virtual_keyboard.StoppedPartway):
        virtual_keyboard.send([(42, 1), (30, 1), (30, 0), (42, 0)])
    assert keyboard.closed and virtual_keyboard._device is None


def test_keys_left_down_are_let_go(keyboard):
    """A Shift left down on any keyboard capitalises what the user types next."""
    virtual_keyboard.send([(42, 1), (30, 1), (30, 0)])
    assert keyboard.events[-1] == (42, 0)


def test_without_access_to_uinput_nothing_is_typed(monkeypatch):
    monkeypatch.setattr(virtual_keyboard, "_open", lambda: None)
    monkeypatch.setattr(app, "_which", lambda name: None)
    assert app._type_text_raw("hello") is False


def test_an_undo_stopped_partway_forgets_the_buffer(monkeypatch):
    """Most of the text may be gone already, so keeping the buffer would make
    the next undo backspace that many characters again, into the user's own
    writing."""
    monkeypatch.setattr(app, "_beep", lambda *a, **k: None)
    monkeypatch.setattr(app, "_notify", lambda *a, **k: None)

    def partway(count):
        raise virtual_keyboard.StoppedPartway("backspaces")

    monkeypatch.setattr(app, "_send_backspaces", partway)
    app.state.last_inserted_text = "a long dictation that was being undone"
    try:
        assert app._handle_undo("undo last sentence", beeps_on=False, notify_on=False) is True
        assert app.state.last_inserted_text == ""
    finally:
        app.state.last_inserted_text = ""


# --- its shape ---------------------------------------------------------------

def test_the_installed_hotkey_helper_skips_it_too():
    """Helpers already on users' computers skip pointers, as they skipped
    ydotoold's device; ours must look like one to them."""
    from tuxtalk import hotkey_helper
    caps = virtual_keyboard._capabilities()
    from evdev import ecodes
    assert hotkey_helper.REL_X in caps[ecodes.EV_REL]
    assert hotkey_helper.BTN_LEFT in caps[ecodes.EV_KEY]


def test_it_has_every_key_a_layout_can_type_and_no_joystick_buttons():
    """A joystick button would make udev call it a game controller."""
    from evdev import ecodes
    keys = set(virtual_keyboard._capabilities()[ecodes.EV_KEY])
    assert set(range(1, 249)) <= keys
    assert not keys & {ecodes.BTN_TRIGGER, ecodes.BTN_SOUTH, ecodes.BTN_TRIGGER_HAPPY1}


def test_a_shortcut_cut_off_partway_reports_failure(keyboard):
    """Ctrl+V that broke after Ctrl went down: the paste didn't happen."""
    keyboard.fail_after = 1
    assert app._send_keys([(29, 1), (47, 1), (47, 0), (29, 0)], what="paste") is False

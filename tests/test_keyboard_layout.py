"""Typing on non-US keyboard layouts (GitHub issue #8).

ydotool turns characters into US key positions, so on a Swiss German keyboard
"my keyboard is lazy" came out as "mz kezboard is layz". keyboard_layout works
out the right physical keys for the active layout instead.

Every mapping test replays the planned keys through libxkbcommon, the same
library the compositor uses to turn key presses into characters, including
dead-key composition, so these check the text a user would actually get.
"""
import ctypes as C
import json

import pytest

from talktype import keyboard_layout as kl

xkb = pytest.importorskip("ctypes").CDLL("libxkbcommon.so.0")
P = C.c_void_p
xkb.xkb_state_new.restype = P
xkb.xkb_state_new.argtypes = [P]
xkb.xkb_state_update_key.argtypes = [P, C.c_uint32, C.c_int]
xkb.xkb_state_key_get_one_sym.argtypes = [P, C.c_uint32]
xkb.xkb_state_key_get_one_sym.restype = C.c_uint32
xkb.xkb_state_key_get_utf8.argtypes = [P, C.c_uint32, C.c_char_p, C.c_size_t]
xkb.xkb_compose_table_new_from_locale.restype = P
xkb.xkb_compose_table_new_from_locale.argtypes = [P, C.c_char_p, C.c_int]
xkb.xkb_compose_state_new.restype = P
xkb.xkb_compose_state_new.argtypes = [P, C.c_int]
xkb.xkb_compose_state_feed.argtypes = [P, C.c_uint32]
xkb.xkb_compose_state_get_status.argtypes = [P]
xkb.xkb_compose_state_get_utf8.argtypes = [P, C.c_char_p, C.c_size_t]
xkb.xkb_compose_state_reset.argtypes = [P]
COMPOSED, CANCELLED, COMPOSING = 2, 3, 1


def replay(planner, tokens):
    """The text a compositor using this layout would produce from `tokens`
    (ydotool "keycode:pressed" strings), dead keys included."""
    state = xkb.xkb_state_new(planner.keymap)
    table = xkb.xkb_compose_table_new_from_locale(planner.ctx, b"en_US.UTF-8", 0)
    compose = xkb.xkb_compose_state_new(table, 0)
    buf = C.create_string_buffer(32)
    out = ""
    for token in tokens:
        code, pressed = (int(v) for v in token.split(":"))
        kc = code + 8
        if pressed:
            sym = xkb.xkb_state_key_get_one_sym(state, kc)
            xkb.xkb_compose_state_feed(compose, sym)
            status = xkb.xkb_compose_state_get_status(compose)
            if status == COMPOSED:
                xkb.xkb_compose_state_get_utf8(compose, buf, 32)
                out += buf.value.decode()
                xkb.xkb_compose_state_reset(compose)
            elif status != COMPOSING:
                if status == CANCELLED:
                    xkb.xkb_compose_state_reset(compose)
                xkb.xkb_state_key_get_utf8(state, kc, buf, 32)
                out += buf.value.decode()
        xkb.xkb_state_update_key(state, kc, 1 if pressed else 0)
    return out


@pytest.mark.parametrize("layout, variant", [("ch", ""), ("ch", "fr"), ("de", ""), ("fr", ""),
                                             ("gb", ""), ("us", "intl"), ("us", "dvorak")])
def test_ordinary_dictation_types_correctly(layout, variant):
    planner = kl.KeyPlanner(layout, variant)
    text = 'My keyboard is lazy. Yes, 50% done (really?) "quoted" it\'s 3:45, ok!'
    assert replay(planner, planner.plan(text)) == text


def test_swiss_german_letters_and_symbols():
    planner = kl.KeyPlanner("ch", "")
    text = "Zürich, Ärger, Öl, Übung, é à è, ç @ # € $ £"
    assert replay(planner, planner.plan(text)) == text


def test_y_and_z_use_the_keys_where_they_really_are():
    """The reported bug, as raw keys: on QWERTZ, y is evdev key 44 (US z)."""
    planner = kl.KeyPlanner("ch", "")
    assert planner.plan("y") == ["44:1", "44:0"]
    assert planner.plan("z") == ["21:1", "21:0"]


def test_a_capital_umlaut_uses_the_accent_key_then_the_letter():
    """Swiss keyboards have no Ä key; ¨ then Shift+A composes it."""
    planner = kl.KeyPlanner("ch", "")
    tokens = planner.plan("Ä")
    assert len(tokens) > 4 and replay(planner, tokens) == "Ä"


def test_text_the_layout_cannot_type_is_reported_not_garbled():
    planner = kl.KeyPlanner("de", "")
    assert planner.plan("Thumbs up 👍") is None
    assert kl.KeyPlanner("ru", "").plan("hello") is None      # no Latin letters


def test_us_keyboards_keep_the_old_typing_path():
    assert kl.needs_layout_typing(("us", ""), "anything") is False
    assert kl.needs_layout_typing(None, "anything") is False          # unknown layout
    assert kl.needs_layout_typing(("ch", ""), "anything") is True
    assert kl.needs_layout_typing(("us", "intl"), "anything") is True  # dead-key variant


# --- finding the active layout ---------------------------------------------------

def test_kde_reports_the_active_layout(monkeypatch):
    monkeypatch.setattr(kl, "_kde_layouts", lambda: ([("us", ""), ("ch", "fr")], 1))
    monkeypatch.setattr(kl, "_desktop", lambda: "kde")
    assert kl.active_layout() == ("ch", "fr")


@pytest.mark.parametrize("mru, sources, expected", [
    ("[('xkb', 'ch'), ('xkb', 'us')]", "[('xkb', 'us'), ('xkb', 'ch')]", ("ch", "")),
    ("@a(ss) []", "[('xkb', 'de+nodeadkeys')]", ("de", "nodeadkeys")),
    ("@a(ss) []", "[('ibus', 'anthy')]", None),
])
def test_gnome_reports_the_active_layout(monkeypatch, mru, sources, expected):
    values = {"mru-sources": mru, "sources": sources}
    monkeypatch.setattr(kl, "_gsettings", lambda key: values[key])
    monkeypatch.setattr(kl, "_desktop", lambda: "gnome")
    monkeypatch.setattr(kl, "_system_layout", lambda: None)
    assert kl.active_layout() == expected


def test_hyprland_reports_the_active_layout(monkeypatch):
    devices = {"keyboards": [
        {"name": "virtual-keyboard", "main": False, "layout": "us", "variant": ""},
        {"name": "logitech", "main": True, "layout": "ch,us", "variant": "fr,",
         "active_layout_index": 0}]}
    monkeypatch.setattr(kl, "_hyprland_devices", lambda: devices)
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "x")
    assert kl.active_layout() == ("ch", "fr")


def test_sway_reports_the_active_layout_by_its_description(monkeypatch):
    inputs = [{"type": "pointer"},
              {"type": "keyboard", "xkb_active_layout_index": 1,
               "xkb_layout_names": ["English (US)", "German (Switzerland)"]}]
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    monkeypatch.setenv("SWAYSOCK", "/x")
    monkeypatch.setattr(kl, "_sway_inputs", lambda: inputs)
    assert kl.active_layout() == ("ch", "")


def test_x11_reports_the_layout(monkeypatch):
    monkeypatch.setattr(kl, "_desktop", lambda: "xfce")
    monkeypatch.setattr(kl, "_setxkbmap_query",
                        lambda: "rules:      evdev\nmodel:      pc105\nlayout:     fr,us\nvariant:    oss,\n")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert kl.active_layout() == ("fr", "oss")


def test_the_system_setting_is_the_last_resort(monkeypatch, tmp_path):
    conf = tmp_path / "00-keyboard.conf"
    conf.write_text('Section "InputClass"\n  Option "XkbLayout" "ch"\n  Option "XkbVariant" "de_nodeadkeys"\nEndSection\n')
    monkeypatch.setattr(kl, "_XORG_KEYBOARD_CONF", str(conf))
    monkeypatch.setattr(kl, "_DEBIAN_KEYBOARD", str(tmp_path / "missing"))
    assert kl._system_layout() == ("ch", "de_nodeadkeys")
    debian = tmp_path / "keyboard"
    debian.write_text('XKBMODEL="pc105"\nXKBLAYOUT="de"\nXKBVARIANT=""\n')
    monkeypatch.setattr(kl, "_XORG_KEYBOARD_CONF", str(tmp_path / "missing"))
    monkeypatch.setattr(kl, "_DEBIAN_KEYBOARD", str(debian))
    assert kl._system_layout() == ("de", "")


def test_a_detection_failure_means_unknown(monkeypatch):
    def broken():
        raise RuntimeError("no D-Bus")
    monkeypatch.setattr(kl, "_desktop", lambda: "kde")
    monkeypatch.setattr(kl, "_kde_layouts", broken)
    monkeypatch.setattr(kl, "_system_layout", lambda: None)
    assert kl.active_layout() is None


# --- the dictation service uses it -------------------------------------------------

@pytest.fixture
def typing(monkeypatch):
    from talktype import app
    calls = []
    monkeypatch.setattr(app, "_which", lambda name: name == "ydotool")
    monkeypatch.setattr(app, "_ydotool_key", lambda keys, **kw: calls.append(("key", list(keys))) or True)
    monkeypatch.setattr(app, "_paste_text", lambda text, **kw: calls.append(("paste", text)) or True)

    class Done:
        returncode = 0

        def communicate(self, input=None, timeout=None):
            calls.append(("type", input.decode()))
            return b"", b""

    monkeypatch.setattr(app.subprocess, "Popen", lambda *a, **k: Done())
    return app, calls


def test_type_mode_on_a_swiss_keyboard_sends_the_right_keys(typing, monkeypatch):
    app, calls = typing
    monkeypatch.setattr(kl, "active_layout", lambda: ("ch", ""))
    assert app._type_text_raw("my") is True
    (kind, args), = calls
    assert kind == "key" and args[0] == "-d"
    assert args[2:] == ["50:1", "50:0", "44:1", "44:0"]      # m, then y on the Z key


def test_type_mode_on_a_us_keyboard_is_unchanged(typing, monkeypatch):
    app, calls = typing
    monkeypatch.setattr(kl, "active_layout", lambda: ("us", ""))
    assert app._type_text_raw("my keyboard") is True
    assert calls == [("type", "my keyboard")]


def test_untypable_text_is_pasted_instead(typing, monkeypatch):
    app, calls = typing
    monkeypatch.setattr(kl, "active_layout", lambda: ("de", ""))
    assert app._type_text_raw("nice 👍") is True
    assert calls == [("paste", "nice 👍")]


def test_the_electron_fast_path_is_layout_aware_too(typing, monkeypatch):
    app, calls = typing
    monkeypatch.setattr(kl, "active_layout", lambda: ("ch", ""))
    assert app._type_text_fast("z") is True
    assert calls and calls[0][0] == "key" and "21:1" in calls[0][1]

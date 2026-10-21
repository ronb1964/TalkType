"""Typing on non-US keyboard layouts (GitHub issue #8).

Pressing every character's US key position, as ydotool did, makes "my keyboard
is lazy" come out as "mz kezboard is layz" on a Swiss German keyboard.
keyboard_layout works out the right physical keys for the active layout
instead.

Every mapping test replays the planned keys through libxkbcommon, the same
library the compositor uses to turn key presses into characters, including
dead-key composition, so these check the text a user would actually get.
"""
import ctypes as C
import json

import pytest

from tuxtalk import keyboard_layout as kl

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
    ((evdev keycode, pressed) pairs), dead keys included."""
    state = xkb.xkb_state_new(planner.keymap)
    table = xkb.xkb_compose_table_new_from_locale(planner.ctx, b"en_US.UTF-8", 0)
    compose = xkb.xkb_compose_state_new(table, 0)
    buf = C.create_string_buffer(32)
    out = ""
    for code, pressed in tokens:
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
    text = "Zürich, Ärger, Öl, Übung, é à è, ç @ # $ £"
    assert replay(planner, planner.plan(text)) == text


def test_swiss_german_euro_sign():
    """AltGr+E. Ubuntu 22.04's keyboard data (xkb-data 2.33, which the CI
    runs) has no € on the Swiss layout; newer data does. Without it the text
    is untypable on keys and TuxTalk types it another way (UntypableText)."""
    planner = kl.KeyPlanner("ch", "")
    if planner.plan("€") is None:
        pytest.skip("this system's keyboard data has no € on the Swiss layout")
    assert replay(planner, planner.plan("Preis: 5 €")) == "Preis: 5 €"


def test_y_and_z_use_the_keys_where_they_really_are():
    """As raw keys: on QWERTZ, y is evdev key 44 (US z)."""
    planner = kl.KeyPlanner("ch", "")
    assert planner.plan("y") == [(44, 1), (44, 0)]
    assert planner.plan("z") == [(21, 1), (21, 0)]


def test_a_capital_umlaut_uses_the_accent_key_then_the_letter():
    """Swiss keyboards have no Ä key; ¨ then Shift+A composes it."""
    planner = kl.KeyPlanner("ch", "")
    tokens = planner.plan("Ä")
    assert len(tokens) > 4 and replay(planner, tokens) == "Ä"


def test_text_the_layout_cannot_type_is_reported_not_garbled():
    planner = kl.KeyPlanner("de", "")
    assert planner.plan("Thumbs up 👍") is None
    assert kl.KeyPlanner("ru", "").plan("hello") is None      # no Latin letters


def test_a_us_keyboard_types_every_printable_ascii_character_and_tab():
    planner = kl.planner_for(kl.US)
    text = "".join(chr(c) for c in range(32, 127)) + "\t"
    assert replay(planner, planner.plan(text)) == text


def test_a_layout_that_cant_be_read_is_typed_as_us(monkeypatch):
    monkeypatch.setattr(kl, "active_layout", lambda: None)
    assert replay(kl.planner_for(kl.US), kl.layout_key_events("Yes, 50%!")) == "Yes, 50%!"


def test_a_smart_apostrophe_on_a_us_keyboard_is_untypable_not_garbled():
    """US has no key for it; the dictation is pasted instead (app._type_text_raw)."""
    planner = kl.planner_for(kl.US)
    assert planner.plan("I\u2019m") is None


def test_a_layout_libxkbcommon_doesnt_know_is_typed_as_us(monkeypatch):
    """A custom layout: typed as US, as ydotool did, not left untyped."""
    monkeypatch.setattr(kl, "active_layout", lambda: ("no-such-layout", ""))
    assert replay(kl.planner_for(kl.US), kl.layout_key_events("Hi there")) == "Hi there"


def test_a_us_less_than_sign_uses_shift_and_comma():
    """The <> key beside the left Shift is missing on US keyboards, and a
    desktop set to a US model may map nothing to it."""
    assert kl.planner_for(kl.US).plan("<>") == [(42, 1), (51, 1), (51, 0), (42, 0),
                                                (42, 1), (52, 1), (52, 0), (42, 0)]
    assert kl.KeyPlanner("de", "").plan("<") == [(86, 1), (86, 0)]     # its only key there


def test_the_blocking_character_is_named():
    """Naming it saves matching timestamps to find which dictation fell back."""
    assert kl.KeyPlanner("ua", "").plan_or_blocker("Це Windows 10") == (None, "W")
    tokens, blocker = kl.KeyPlanner("ua", "").plan_or_blocker("Привіт, світе.")
    assert tokens and blocker is None


def test_untypable_text_raises_with_the_layout_and_character(monkeypatch):
    monkeypatch.setattr(kl, "active_layout", lambda: ("us", ""))
    with pytest.raises(kl.UntypableText) as e:
        kl.layout_key_events("Привіт")
    assert e.value.args == (("us", ""), "П")


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


def _x11(monkeypatch, layouts, variants, group):
    monkeypatch.setattr(kl, "_desktop", lambda: "lxqt")
    monkeypatch.setattr(kl, "_setxkbmap_query", lambda: (
        f"rules:      evdev\nmodel:      pc105\nlayout:     {layouts}\n"
        + (f"variant:    {variants}\n" if variants is not None else "")))
    monkeypatch.setattr(kl, "_x11_active_group", lambda: group)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")


def test_x11_reports_the_layout(monkeypatch):
    _x11(monkeypatch, "fr,us", "oss,", 0)
    assert kl.active_layout() == ("fr", "oss")


def test_x11_reports_the_layout_that_is_on_not_the_first(monkeypatch):
    """"us,ua" with Ukrainian active must not be typed as US, which turns
    Ukrainian into 9s with commas and full stops as б and ю."""
    _x11(monkeypatch, "us,ua", None, 1)
    assert kl.active_layout() == ("ua", "")


def test_x11_never_gives_the_first_layouts_variant_to_another(monkeypatch):
    _x11(monkeypatch, "us,ua", "dvorak", 1)
    assert kl.active_layout() == ("ua", "")


@pytest.mark.parametrize("group", [None, 7])
def test_x11_without_a_usable_group_uses_the_first(monkeypatch, group):
    _x11(monkeypatch, "us,ua", ",", group)
    assert kl.active_layout() == ("us", "")


def test_x11_group_failure_is_not_fatal(monkeypatch):
    _x11(monkeypatch, "de,us", None, 0)

    def broken():
        raise OSError("no libX11")

    monkeypatch.setattr(kl, "_x11_active_group", broken)
    assert kl.active_layout() == ("de", "")


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
def typing(monkeypatch, keyboard):
    from tuxtalk import app
    calls = []
    monkeypatch.setattr(app, "_paste_text", lambda text, **kw: calls.append(("paste", text)) or True)
    monkeypatch.setattr(app, "_paste_text_x11", lambda text: calls.append(("x11 paste", text)) or True)
    monkeypatch.setattr(app, "_is_wayland_session", lambda: True)
    return app, calls


def test_type_mode_on_a_swiss_keyboard_sends_the_right_keys(typing, keyboard, monkeypatch):
    app, calls = typing
    monkeypatch.setattr(kl, "active_layout", lambda: ("ch", ""))
    assert app._type_text_raw("my") is True
    assert keyboard.events == [(50, 1), (50, 0), (44, 1), (44, 0)]   # m, then y on the Z key


def test_type_mode_on_a_us_keyboard_types_us_keys(typing, keyboard, monkeypatch):
    app, calls = typing
    monkeypatch.setattr(kl, "active_layout", lambda: ("us", ""))
    assert app._type_text_raw("my keyboard") is True
    assert replay(kl.planner_for(kl.US), keyboard.events) == "my keyboard"
    assert not calls


def test_untypable_text_is_pasted_instead(typing, keyboard, monkeypatch):
    app, calls = typing
    monkeypatch.setattr(kl, "active_layout", lambda: ("de", ""))
    assert app._type_text_raw("nice 👍") is True
    assert calls == [("paste", "nice 👍")]
    assert not keyboard.events, "typed part of a dictation that was then pasted whole"


def test_untypable_text_on_x11_uses_the_x11_clipboard(typing, monkeypatch):
    """wl-copy can't reach an X11 display, so _paste_text refuses there."""
    app, calls = typing
    monkeypatch.setattr(app, "_is_wayland_session", lambda: False)
    monkeypatch.setattr(kl, "active_layout", lambda: ("ua", ""))
    assert app._type_text_raw("Це Windows 10") is True
    assert calls == [("x11 paste", "Це Windows 10")]


def test_ukrainian_on_a_ukrainian_layout_is_typed(typing, keyboard, monkeypatch):
    app, calls = typing
    monkeypatch.setattr(kl, "active_layout", lambda: ("ua", ""))
    assert app._type_text_raw("Привіт") is True
    assert replay(kl.planner_for(("ua", "")), keyboard.events) == "Привіт"


def test_cyrillic_on_a_us_layout_is_pasted_not_typed(typing, monkeypatch):
    app, calls = typing
    monkeypatch.setattr(kl, "active_layout", lambda: ("us", ""))
    assert app._type_text_raw("Привіт") is True
    assert calls == [("paste", "Привіт")]


# --- the layout registry (Sway names layouts by description) ---------------

class _FakeRegistry:
    """Enough of libxkbregistry for the description lookup, counting how
    often the registry is parsed and freed."""

    LAYOUTS = [(b"German (Switzerland)", b"ch", b""), (b"English (US)", b"us", b""),
               (b"English (US)", b"us", b"intl")]

    def __init__(self):
        self.parsed = self.freed = 0
        reg = self

        def fn(f):
            return type("Fn", (), {"__call__": staticmethod(f)})()
        self.rxkb_context_new = fn(lambda flags: 1)
        self.rxkb_context_parse_default_ruleset = fn(self._parse)
        self.rxkb_context_unref = fn(self._unref)
        self.rxkb_layout_first = fn(lambda ctx: 1)
        self.rxkb_layout_next = fn(lambda i: i + 1 if i < len(reg.LAYOUTS) else None)
        self.rxkb_layout_get_description = fn(lambda i: reg.LAYOUTS[i - 1][0])
        self.rxkb_layout_get_name = fn(lambda i: reg.LAYOUTS[i - 1][1])
        self.rxkb_layout_get_variant = fn(lambda i: reg.LAYOUTS[i - 1][2])

    def _parse(self, ctx):
        self.parsed += 1
        return True

    def _unref(self, ctx):
        self.freed += 1


def test_the_registry_is_parsed_once_and_freed(monkeypatch):
    """Parsing the whole XKB registry for every typed chunk on Sway, and
    never freeing it, would waste time and memory."""
    import ctypes
    from tuxtalk import keyboard_layout as kl
    fake = _FakeRegistry()
    monkeypatch.setattr(kl, "_registry_table", None)
    monkeypatch.setattr(ctypes, "CDLL", lambda name: fake)
    assert kl._layout_from_description("German (Switzerland)") == ("ch", "")
    assert kl._layout_from_description("English (US)") == ("us", "")   # first match wins
    assert kl._layout_from_description("Klingon") is None
    assert (fake.parsed, fake.freed) == (1, 1)

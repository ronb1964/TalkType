"""After a hotkey change, Preferences offers the hotkey test and says when
KDE already uses the key, as first run does, instead of leaving KDE's refusal
in the log only."""
import pytest

pytest.importorskip("gi")
from tuxtalk.prefs import hotkey_change_message, hotkey_label  # noqa: E402

CFG = {"hotkey": "F7", "toggle_hotkey": "F9", "voice_commands_hotkey": "Ctrl+Alt+V"}


def test_a_new_hold_key_offers_the_test_and_warns_about_laptop_fn_keys():
    _title, text, offer_test = hotkey_change_message(CFG, {"hotkey"}, [])
    assert offer_test and "hold-to-talk key is now F7" in text and "Fn" in text


def test_both_keys_are_named():
    _title, text, _ = hotkey_change_message(CFG, {"hotkey", "toggle_hotkey"}, None)
    assert "F7" in text and "F9" in text


def test_a_key_kde_already_uses_is_said_on_screen():
    _title, text, offer_test = hotkey_change_message(CFG, {"hotkey"}, ["F7"])
    assert offer_test and "KDE already uses F7" in text


def test_only_the_voice_commands_key_changed_has_no_test_to_offer():
    assert hotkey_change_message(CFG, {"voice_commands_hotkey"}, []) is None
    _title, text, offer_test = hotkey_change_message(CFG, {"voice_commands_hotkey"}, ["Ctrl+Alt+V"])
    assert not offer_test and "KDE already uses Ctrl+Alt+V" in text


def test_no_hotkey_change_says_nothing():
    assert hotkey_change_message(CFG, {"model"}, ["F7"]) is None


def test_keys_apps_already_use_are_labelled_in_the_dropdowns():
    assert hotkey_label("F5") == "F5 (reloads the page in browsers)"
    assert hotkey_label("F8") == "F8"


def test_kdes_meta_spelling_maps_back_to_super():
    cfg = dict(CFG, voice_commands_hotkey="Ctrl+Super+V")
    _title, text, _ = hotkey_change_message(cfg, {"voice_commands_hotkey"}, ["Ctrl+Meta+V"])
    assert "KDE already uses Ctrl+Super+V" in text


def test_the_question_says_where_to_test_later():
    _title, text, _ = hotkey_change_message(CFG, {"hotkey"}, [])
    assert "Test Hotkeys, under the hotkeys on the General tab" in text


def test_an_app_kde_opens_with_the_key_is_named_first():
    """F6 opened the Emoji Selector as well as dictating (2026-10-13). The
    clash leads, title and all, for someone who reads only the top."""
    cfg = dict(CFG, hotkey="F6")
    title, text, offer_test = hotkey_change_message(cfg, {"hotkey"}, ["F6"],
                                                    {"F6": "Emoji Selector"})
    assert title == "Heads up: F6 also opens Emoji Selector"
    assert text.startswith("KDE opens Emoji Selector with F6")
    assert "System Settings" in text and offer_test
    assert "one of its own shortcuts" not in text


def test_a_kde_shortcut_clash_leads_too():
    title, text, _ = hotkey_change_message(CFG, {"hotkey"}, ["F7"])
    assert title == "Heads up: KDE already uses F7"
    assert text.startswith("KDE already uses F7")


def test_several_clashes_get_one_title():
    cfg = dict(CFG, hotkey="F6")
    title, _, _ = hotkey_change_message(cfg, {"hotkey"}, ["F6", "F9"], {"F6": "Emoji Selector"})
    assert title == "Heads up: KDE already uses some of these keys"


def test_no_clash_asks_to_try_the_key():
    title, _, _ = hotkey_change_message(CFG, {"hotkey"}, [])
    assert title == "Try your new hotkey?"

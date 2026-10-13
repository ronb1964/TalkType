"""Swiss German spelling: ß becomes ss (GitHub issue #10).

Swiss Standard German never writes ß, but Parakeet and Whisper do. The option
swaps it in the finished text, so it works the same with every engine.
"""
import pytest

from tuxtalk import app, config
from tuxtalk.normalize import swiss_spelling


@pytest.mark.parametrize("text, expected", [
    ("Die Straße ist groß.", "Die Strasse ist gross."),
    ("Fuß", "Fuss"),
    ("ß", "ss"),
    ("STRAßE", "STRASSE"),            # an all-caps word keeps its capitals
    ("STRAẞE", "STRASSE"),            # the capital sharp s
    ("ẞ", "SS"),
    ("Grüße aus Zürich", "Grüsse aus Zürich"),
    ("no sharp s here", "no sharp s here"),
])
def test_sharp_s_becomes_ss(text, expected):
    assert swiss_spelling(text) == expected


@pytest.mark.parametrize("env, expected", [
    ({"LANG": "de_CH.UTF-8"}, True),
    ({"LC_ALL": "de_CH.UTF-8", "LANG": "en_US.UTF-8"}, True),
    ({"LANGUAGE": "de_CH:de", "LANG": "en_US.UTF-8"}, True),
    ({"LANG": "gsw_CH.UTF-8"}, True),             # Swiss German's own locale
    ({"LANG": "fr_CH.UTF-8"}, False),             # Swiss, but French
    ({"LANG": "de_DE.UTF-8"}, False),
    ({"LANG": "en_US.UTF-8"}, False),
    ({}, False),
])
def test_on_by_default_only_on_swiss_german_systems(env, expected):
    assert config.swiss_german_locale(env) is expected


def test_the_default_follows_the_system_locale(monkeypatch):
    for var in ("LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "de_CH.UTF-8")
    assert config.Settings().swiss_spelling is True
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert config.Settings().swiss_spelling is False


def test_it_applies_without_a_restart():
    assert "swiss_spelling" in config.LIVE_APPLIED_KEYS


def _prepare(monkeypatch, on):
    monkeypatch.setattr(app, "_swiss_spelling", on)
    monkeypatch.setattr(app, "_custom_words", [])
    monkeypatch.setattr(app, "_remove_fillers", False)
    monkeypatch.setattr(app, "_ai_corrections", False)
    return app._prepare_text("die straße ist groß", smart_quotes=True,
                             auto_period=True, auto_space=False)


def test_dictation_uses_ss_when_on(monkeypatch):
    assert _prepare(monkeypatch, True) == "Die strasse ist gross."


def test_dictation_keeps_sharp_s_when_off(monkeypatch):
    assert _prepare(monkeypatch, False) == "Die straße ist groß."


def test_the_setting_is_read_on_each_reload(monkeypatch):
    monkeypatch.setattr(app, "_ai_engine", None)
    app._apply_cleanup_settings(config.Settings(swiss_spelling=True))
    assert app._swiss_spelling is True
    app._apply_cleanup_settings(config.Settings(swiss_spelling=False))
    assert app._swiss_spelling is False


def test_preferences_has_the_checkbox_bound_to_the_setting():
    from tuxtalk.prefs import PreferencesWindow
    changes = []

    class Stub:
        config = {"swiss_spelling": True}

        def update_config(self, key, value):
            changes.append((key, value))

    check = PreferencesWindow._swiss_spelling_check(Stub())
    assert check.get_active() is True and "ß" in check.get_label()
    check.set_active(False)
    assert changes == [("swiss_spelling", False)]

"""Privacy: transcribed text is kept out of the on-disk log by default.

TalkType logs every raw/normalized transcription to ~/.config/talktype/talktype.log
for troubleshooting. That is a standing plaintext record of everything the user
dictates. It must be redacted by default and only revealed when the user opts in
via the `log_transcripts` setting (which pops a warning before it turns on).
"""
import pathlib

from talktype import config
from talktype import logger as tlog

PREFS = pathlib.Path(__file__).resolve().parent.parent / "src/talktype/prefs.py"


# --- config flag -----------------------------------------------------------

def test_log_transcripts_defaults_off():
    assert config.Settings().log_transcripts is False


def test_log_transcripts_applies_live_no_restart():
    """Toggling it in Preferences should take effect without a service restart."""
    assert "log_transcripts" in config.LIVE_APPLIED_KEYS
    assert "log_transcripts" not in config.RESTART_REQUIRED_KEYS


# --- redaction helper ------------------------------------------------------

def test_redact_hides_content_but_keeps_length_by_default():
    assert tlog.redact_text("hello world") == "[hidden, 11 chars]"


def test_redact_reveals_full_repr_when_opted_in():
    # repr form matches the old `{text!r}` logging exactly, so an opted-in log
    # reads identically to before.
    assert tlog.redact_text("hello world", reveal=True) == "'hello world'"


def test_redact_is_robust_to_non_strings():
    assert tlog.redact_text(None) == "[hidden]"


# --- app wiring: the service's live flag gates redaction -------------------

def test_app_defaults_to_not_logging_transcripts():
    from talktype import app
    assert app._log_transcripts is False


def test_app_loggable_respects_the_live_flag(monkeypatch):
    from talktype import app
    monkeypatch.setattr(app, "_log_transcripts", False)
    assert app._loggable("secret words") == "[hidden, 12 chars]"
    monkeypatch.setattr(app, "_log_transcripts", True)
    assert app._loggable("secret words") == "'secret words'"


# --- end-to-end: a real logging site keeps the words out of the log --------

def test_custom_command_log_line_redacts_the_text(monkeypatch, caplog):
    """Drives a real logging site: with the flag off, the emitted log record
    must not contain the dictated words, only the redacted breadcrumb. Guards
    against a future edit reverting `{_loggable(x)}` back to `{x!r}`."""
    import logging
    from talktype import app
    monkeypatch.setattr(app, "_log_transcripts", False)
    monkeypatch.setattr(app, "_custom_commands", {"banana": "apple"})
    secret = "my banana passphrase"
    with caplog.at_level(logging.INFO, logger="talktype.app"):
        app._apply_custom_commands(secret)
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "Custom commands applied" in logged   # the line did fire
    assert "banana" not in logged                 # ...but the words are gone
    assert "[hidden," in logged


# --- prefs UI: opt-in checkbox with a warning gate -------------------------

def test_prefs_has_log_transcripts_checkbox():
    text = PREFS.read_text()
    assert "Log transcribed text" in text
    assert "log_transcripts" in text
    assert "_on_log_transcripts_toggled" in text


def test_enabling_logging_is_gated_by_a_warning_dialog():
    """Turning ON transcript logging must confirm via a WARNING dialog before it
    writes the config, so the user is fully aware their dictation will be saved."""
    text = PREFS.read_text()
    assert "MessageType.WARNING" in text
    # The handler that shows the warning references the setting it guards.
    assert "_on_log_transcripts_toggled" in text


def test_injection_tooltip_no_longer_claims_password_field_handling():
    """The old Auto-mode tooltip claimed it types into password fields and uses
    AT-SPI — both false (AT-SPI is unreachable; nothing detects password fields).
    That misleading copy must be gone."""
    text = PREFS.read_text()
    assert "Typing for password fields" not in text
    assert "AT-SPI when available" not in text


# --- the enable gate is enforced (drives the real handler) -----------------

def _fake_check(active):
    import types
    reverted = []
    check = types.SimpleNamespace(
        get_active=lambda: active,
        set_active=lambda v: reverted.append(v),
        handler_block_by_func=lambda f: None,
        handler_unblock_by_func=lambda f: None,
    )
    return check, reverted


def _install_fake_dialog(monkeypatch, response):
    from talktype import prefs
    seen = {}

    class _FakeStyle:
        def add_class(self, *a):
            pass

    class _FakeButton:
        def get_style_context(self):
            return _FakeStyle()

    class _FakeDialog:
        def __init__(self, **kw):
            seen["message_type"] = kw.get("message_type")
            seen["transient_for"] = kw.get("transient_for")

        def format_secondary_text(self, t):
            seen["secondary"] = t

        def add_button(self, label, resp):
            seen.setdefault("buttons", []).append(label)
            return _FakeButton()

        def set_default_response(self, r):
            seen["default"] = r

        def run(self):
            return response

        def destroy(self):
            pass

    monkeypatch.setattr(prefs.Gtk, "MessageDialog", _FakeDialog)
    return seen


def test_checking_the_box_without_confirming_does_not_enable_logging(monkeypatch):
    import types
    from talktype import prefs
    seen = _install_fake_dialog(monkeypatch, prefs.Gtk.ResponseType.CANCEL)
    saved = []
    window = object()  # stands in for the real Gtk.Window at self.window
    self = types.SimpleNamespace(update_config=lambda k, v: saved.append((k, v)),
                                 window=window,
                                 _on_log_transcripts_toggled=lambda *a: None)
    check, reverted = _fake_check(active=True)

    prefs.PreferencesWindow._on_log_transcripts_toggled(self, check)

    assert seen["message_type"] == prefs.Gtk.MessageType.WARNING  # a warning was shown
    # The dialog must be parented to the real window, not the wrapper — passing
    # the wrapper makes GTK reject it and no modal ever appears.
    assert seen["transient_for"] is window
    assert ("log_transcripts", True) not in saved                 # cancel → not enabled
    assert reverted == [False]                                    # box snapped back off


def test_confirming_the_warning_enables_logging(monkeypatch):
    import types
    from talktype import prefs
    _install_fake_dialog(monkeypatch, prefs.Gtk.ResponseType.OK)
    saved = []
    self = types.SimpleNamespace(update_config=lambda k, v: saved.append((k, v)),
                                 window=object(),
                                 _on_log_transcripts_toggled=lambda *a: None)
    check, _ = _fake_check(active=True)

    prefs.PreferencesWindow._on_log_transcripts_toggled(self, check)

    assert ("log_transcripts", True) in saved                     # confirmed → enabled


def test_unchecking_needs_no_dialog_and_disables(monkeypatch):
    import types
    from talktype import prefs
    # If a dialog were constructed while unchecking, this would blow up.
    monkeypatch.setattr(prefs.Gtk, "MessageDialog",
                        lambda **k: (_ for _ in ()).throw(AssertionError("no dialog on uncheck")))
    saved = []
    self = types.SimpleNamespace(update_config=lambda k, v: saved.append((k, v)),
                                 _on_log_transcripts_toggled=lambda *a: None)
    check, _ = _fake_check(active=False)

    prefs.PreferencesWindow._on_log_transcripts_toggled(self, check)

    assert ("log_transcripts", False) in saved


# --- clearing the log ------------------------------------------------------

def test_log_file_path_follows_dev_mode(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "1")
    assert tlog.log_file_path().parent.name == "talktype-dev"
    monkeypatch.delenv("DEV_MODE", raising=False)
    assert tlog.log_file_path().parent.name == "talktype"


def test_clear_log_empties_main_and_removes_backup(tmp_path):
    main = tmp_path / "talktype.log"
    main.write_text("secret dictation history\n")
    old = tmp_path / "talktype.log.old"
    old.write_text("older secrets\n")

    tlog.clear_log(tmp_path)

    # Truncated (not deleted) so a service holding it open keeps appending.
    assert main.exists() and main.read_text() == ""
    assert not old.exists()


def test_prefs_has_clear_log_button():
    text = PREFS.read_text()
    assert "Clear log" in text
    assert "_on_clear_log_clicked" in text

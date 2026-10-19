"""Test-suite wide setup.

Keep the suite's logging out of the user's real TuxTalk log. Modules create
their file handler at import time, so this has to happen before any test
module imports tuxtalk, which is why it runs at conftest import rather than
in a fixture. Subprocesses started by tests inherit it through the
environment.
"""
import atexit
import os
import shutil
import tempfile

import pytest

_LOG_DIR = tempfile.mkdtemp(prefix="talktype-test-logs-")
os.environ["TUXTALK_LOG_DIR"] = _LOG_DIR
# Never move the real ~/.config/talktype or ~/.local/share/TalkType while the
# suite imports tuxtalk (the rename migration runs on package import).
os.environ["TUXTALK_NO_MIGRATE"] = "1"
atexit.register(shutil.rmtree, _LOG_DIR, ignore_errors=True)


def _hold_back_notifications():
    """Desktop notifications from tests must never reach the user's desktop.

    Patched here, at conftest import, so it covers module-level code too;
    tests that check a message stub app._notify themselves.
    """
    from tuxtalk import notify

    def _held_back(title, body):
        return None

    notify._send = _held_back


_hold_back_notifications()


@pytest.fixture(autouse=True)
def _no_remembered_dictation_window(monkeypatch):
    """Start each test with no remembered dictation window. Typing records the
    focused window (state.last_inserted_window), and undo and voice navigation
    refuse when another window has the focus. A window left by an earlier test
    compared against the user's real desktop, so tests passed or failed with
    whatever the user was doing."""
    from tuxtalk import app
    monkeypatch.setattr(app.state, "last_inserted_window", None)
    monkeypatch.setattr(app.state, "nav_context", None)


@pytest.fixture(autouse=True)
def _no_real_speech_model(monkeypatch):
    """Start each test with a stand-in speech model. Starting a recording
    loads the real one when none is in memory (Power Saving, _wake_model):
    seconds on a computer that has it, a 670 MB download in CI, where the
    suite ran into its 20-minute limit (2026-10-18). Tests of the loading
    itself set app.model to None."""
    from tuxtalk import app
    monkeypatch.setattr(app, "model", object())


@pytest.fixture(autouse=True)
def _no_followed_default_mic(monkeypatch):
    """Start each test without a tracked System Default mic. A test that runs
    the real _pick_input_device("") records the user's PipeWire default, and
    start_recording would then record from that instead of the device the
    next test passes in."""
    from tuxtalk import app
    monkeypatch.setattr(app, "_system_default_mic", None)


@pytest.fixture(autouse=True)
def _no_real_send_countdown(monkeypatch, request):
    """No floating label on the user's screen and no Enter left counting down
    between tests. Sends happen at once unless a test sets a wait itself.
    test_window_messages tests the label itself, with its own fakes."""
    from tuxtalk import app, screen_message
    if request.module.__name__.rpartition(".")[2] != "test_window_messages":
        monkeypatch.setattr(screen_message, "show_over_active_window", lambda *a, **k: None)
        monkeypatch.setattr(screen_message, "hide", lambda *a, **k: None)
        monkeypatch.setattr(screen_message, "relabel", lambda *a, **k: None)
    monkeypatch.setattr(app, "_press_enter_delay", 0.0)
    monkeypatch.setattr(app.state, "pending_send", None)
    monkeypatch.setattr(app.state, "held_send", False)
    monkeypatch.setattr(app.state, "owed_space", None)
    monkeypatch.setattr(app.state, "sent", None)


@pytest.fixture(autouse=True)
def _no_real_explanation_windows(monkeypatch, tmp_path):
    """Never open an explanation window on the user's desktop, and never read
    or write their "don't explain again" choices. Tests that want the window
    record it through explain.open_window themselves."""
    from tuxtalk import explain
    monkeypatch.setattr(explain, "open_window", lambda kind: False)
    monkeypatch.setattr(explain, "_never_path", lambda: str(tmp_path / "explained.json"))


@pytest.fixture(autouse=True)
def _no_real_kwin(monkeypatch):
    """Never let a test register or release hotkeys in the user's live KWin.

    service_launcher.stop_dictation_service() releases them, and on a KDE
    machine running the suite would hand the dev service's F8 back to whatever
    app has focus. Tests of kwin_hotkeys pass their own fake bus.
    """
    from tuxtalk import kwin_hotkeys

    def _refuse():
        raise RuntimeError("tests must not talk to the real KWin")

    monkeypatch.setattr(kwin_hotkeys, "session_bus", _refuse)


@pytest.fixture(autouse=True)
def _no_real_tuxtalk(monkeypatch):
    """Never let a test send commands to the user's running TuxTalk.

    A second tray asks the running one to show its menu window, so a test of
    the single-instance lock opened the menu on Ron's desktop (2026-10-16);
    --toggle could even start a recording. Tests of control pass a fake bus.
    """
    from tuxtalk import control

    def _refuse():
        raise RuntimeError("tests must not talk to the running TuxTalk")

    monkeypatch.setattr(control, "_session_bus", _refuse)


@pytest.fixture(autouse=True)
def _no_real_media_players(monkeypatch):
    """Never let a test pause the user's music.

    Tests that run the service's settings reload turn pause_media on, and later
    tests call the real start_recording. Tests of media_pause pass a fake bus.
    """
    from tuxtalk import media_pause

    def _refuse(self):
        raise RuntimeError("tests must not talk to real media players")

    monkeypatch.setattr(media_pause.SessionBus, "_bus", _refuse)


_HOTKEY_TEST_FLAG = os.path.join(_LOG_DIR, ".hotkey_test_mode")


@pytest.fixture(autouse=True)
def _no_real_hotkey_test_flag(monkeypatch):
    """Keep tests off the real hotkey test flag in the user's data folder.

    Test Hotkeys open in the real Preferences would otherwise turn every key
    press a test sends into a test-mode report. Tests of the flag write here.
    """
    import sys
    from tuxtalk import service_launcher

    monkeypatch.setattr(service_launcher, "hotkey_test_flag_path", lambda: _HOTKEY_TEST_FLAG)
    app = sys.modules.get("tuxtalk.app")
    if app is not None:
        monkeypatch.setattr(app, "_hotkey_test_flag", None)
    yield
    try:
        os.remove(_HOTKEY_TEST_FLAG)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def _no_real_custom_files(monkeypatch, tmp_path):
    """Keep tests off the user's own Your Words and custom commands.

    custom_words.txt sits beside custom_commands.toml, so one path covers
    both. In 0.15.0 testing, "TuxTalk" saved in the real Your Words reached a
    Whisper test as a prompt it didn't expect. Tests that need these files
    point the path at their own folder, as before.
    """
    import sys
    from tuxtalk import config

    monkeypatch.setattr(config, "CUSTOM_COMMANDS_PATH", str(tmp_path / "custom_commands.toml"))
    app = sys.modules.get("tuxtalk.app")
    if app is not None:
        monkeypatch.setattr(app, "_custom_words", [])


@pytest.fixture(autouse=True)
def _no_real_hotkey_helper_or_pkexec(monkeypatch, tmp_path):
    """No test may open a password prompt or reach a real hotkey helper.

    A test that patched only the "input" group installer once ran the real
    pkexec through the hotkey helper's installer instead, and a password
    dialog sat on the desktop until it timed out. So: the helper's socket is
    a path nobody listens on, this machine counts as unable to run the
    helper unless a test says otherwise, and running anything as root fails
    the test outright."""
    monkeypatch.setenv("TUXTALK_HOTKEYS_SOCKET", str(tmp_path / "no-helper.sock"))
    from tuxtalk import secure_input
    monkeypatch.setattr(secure_input, "can_install", lambda: (False, "tests"))

    def refuse(*_a, **_k):
        pytest.fail("a test tried to run something as root through pkexec")
    monkeypatch.setattr(secure_input, "_run_as_root", refuse)

    # And pkexec itself, however it's reached. A test that mocks
    # subprocess.run on purpose replaces this guard with its own mock.
    import subprocess
    real_run = subprocess.run

    def guarded_run(cmd, *args, **kwargs):
        if isinstance(cmd, (list, tuple)) and cmd and os.path.basename(str(cmd[0])) == "pkexec":
            pytest.fail(f"a test tried to run pkexec: {cmd[:3]}")
        return real_run(cmd, *args, **kwargs)
    monkeypatch.setattr(subprocess, "run", guarded_run)


@pytest.fixture(autouse=True)
def _no_real_snippets_or_words(monkeypatch, tmp_path_factory):
    """Snippets (custom_commands.toml) and Your Words (custom_words.txt, beside
    it) live in a throwaway folder for every test. Building Preferences moves
    word fixes into Your Words the first time (vocabulary.adopt_fixes); run
    against the user's real files, a test would do that for real."""
    from tuxtalk import config
    folder = tmp_path_factory.mktemp("snippets")
    monkeypatch.setattr(config, "CUSTOM_COMMANDS_PATH", str(folder / "custom_commands.toml"))

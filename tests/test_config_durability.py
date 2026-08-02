"""Tests for settings surviving crashes, full disks and bad values.

The settings file holds the hotkey. If it is lost or reset, dictation stops
working entirely — and because "setup already done" lives in a *different*
file, onboarding does not re-run to fix it. The user is left with a tray icon
that does nothing and no explanation.
"""

import os

import pytest

from talktype import config


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    """Point the config module at a throwaway file."""
    path = tmp_path / "config.toml"
    monkeypatch.setattr(config, "CONFIG_PATH", str(path))
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(config, "_config_mtime", 0.0)
    return path


# --- atomic writes ---------------------------------------------------------

def test_save_never_leaves_a_truncated_file(config_path, monkeypatch):
    """A full disk mid-write used to leave the file empty, deterministically,
    losing every setting including the hotkey."""
    settings = config.Settings()
    settings.model = "large-v3"
    config.save_config(settings)
    original = config_path.read_text()
    assert "large-v3" in original

    # Fail the write before it can be renamed into place, as a full disk would.
    def no_space(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(config.os, "fsync", no_space)
    settings.model = "tiny"
    with pytest.raises(OSError):
        config.save_config(settings)

    monkeypatch.undo()
    assert config_path.read_text() == original, "the previous settings were destroyed"
    leftovers = [p.name for p in config_path.parent.iterdir() if ".tmp" in p.name]
    assert not leftovers, f"temp file left behind after a failed save: {leftovers}"


def test_save_keeps_a_backup_of_the_previous_settings(config_path):
    first = config.Settings()
    first.model = "base"
    config.save_config(first)

    second = config.Settings()
    second.model = "large-v3"
    config.save_config(second)

    backup = config_path.with_suffix(config_path.suffix + ".bak")
    assert backup.exists(), "no backup written"
    assert "base" in backup.read_text()


def test_saved_settings_round_trip(config_path):
    settings = config.Settings()
    settings.model = "small"
    settings.auto_period = False
    settings.auto_timeout_minutes = 9
    config.save_config(settings)

    loaded = config.load_config()

    assert loaded.model == "small"
    assert loaded.auto_period is False
    assert loaded.auto_timeout_minutes == 9


# --- corrupt config recovery ------------------------------------------------

def test_a_corrupt_config_is_moved_aside_not_silently_reset(config_path):
    good = config.Settings()
    good.model = "small"
    config.save_config(good)

    config_path.write_text("this is not valid toml {{{")
    config._config_cache = None
    config._config_mtime = 0.0

    config.load_config()

    salvaged = list(config_path.parent.glob("config.toml.corrupt-*"))
    assert salvaged, "the damaged file was discarded without a copy"


def test_a_corrupt_config_is_restored_from_backup(config_path):
    # Deliberately not the default model, or this would pass vacuously.
    good = config.Settings()
    good.model = "tiny"
    config.save_config(good)
    # A second save moves the first into .bak
    second = config.Settings()
    second.model = "base"
    config.save_config(second)

    config_path.write_text("garbage {{{")
    config._config_cache = None
    config._config_mtime = 0.0

    loaded = config.load_config()

    assert loaded.model == "tiny", "did not fall back to the last good settings"


def test_an_empty_config_is_treated_as_damaged(config_path):
    """Zero bytes parses fine as TOML, so it silently produced all-defaults —
    including a blank hotkey, which kills dictation with no message."""
    good = config.Settings()
    good.model = "tiny"
    config.save_config(good)
    second = config.Settings()
    second.model = "base"
    config.save_config(second)

    config_path.write_text("")
    config._config_cache = None
    config._config_mtime = 0.0

    loaded = config.load_config()

    assert loaded.model == "tiny"


def test_a_missing_config_is_not_treated_as_damaged(config_path):
    """First run has no file at all. That is normal, not corruption."""
    loaded = config.load_config()

    assert loaded.model == config.Settings().model
    assert not list(config_path.parent.glob("config.toml.corrupt-*"))


# --- validation must not kill the caller ------------------------------------

def test_invalid_settings_raise_instead_of_exiting():
    """validate_config() called sys.exit() from inside a library function that
    the tray runs once per second, so one bad value made the tray icon vanish
    from the panel within a second, with no dialog and no way to tell why."""
    settings = config.Settings()
    settings.injection_mode = "nonsense"

    with pytest.raises(config.ConfigError):
        config.validate_config(settings)


def test_the_error_names_the_setting_that_is_wrong():
    settings = config.Settings()
    settings.injection_mode = "nonsense"

    with pytest.raises(config.ConfigError) as caught:
        config.validate_config(settings)

    assert "injection_mode" in str(caught.value)


def test_valid_settings_validate_cleanly():
    config.validate_config(config.Settings())  # must not raise


def test_loading_a_config_with_one_bad_value_falls_back_for_that_key(config_path):
    """The tray must keep running. A bad value falls back to its default rather
    than taking the whole process down."""
    config_path.write_text('model = "small"\ninjection_mode = "nonsense"\n')
    config._config_cache = None
    config._config_mtime = 0.0

    loaded = config.load_config()

    assert loaded.injection_mode == config.Settings().injection_mode
    assert loaded.model == "small", "unrelated settings were discarded"


# --- custom commands are settings too ---------------------------------------

@pytest.fixture
def commands_path(tmp_path, monkeypatch):
    path = tmp_path / "custom_commands.toml"
    monkeypatch.setattr(config, "CUSTOM_COMMANDS_PATH", str(path))
    return path


def test_custom_commands_round_trip(commands_path):
    commands = {"talk type": "TalkType", "why do tool": "ydotool"}

    config.save_custom_commands(commands)

    assert config.load_custom_commands() == commands


def test_a_quote_in_a_spoken_phrase_does_not_destroy_every_command(commands_path):
    """The replacement was escaped on write but the phrase was not, so one
    command containing a double quote made the whole file unparseable — every
    custom command stopped working at once, and Preferences then showed an
    empty list and wrote it back."""
    commands = {
        'say "hello"': "greeting",
        "talk type": "TalkType",
    }

    config.save_custom_commands(commands)
    loaded = config.load_custom_commands()

    assert loaded == commands


def test_a_backslash_in_a_phrase_survives(commands_path):
    commands = {"back slash": r"C:\Users\Ron", "normal": "fine"}

    config.save_custom_commands(commands)

    assert config.load_custom_commands() == commands


def test_custom_commands_are_written_atomically(commands_path, monkeypatch):
    config.save_custom_commands({"first": "one"})
    original = commands_path.read_text()

    def no_space(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(config.os, "fsync", no_space)
    with pytest.raises(OSError):
        config.save_custom_commands({"second": "two"})

    monkeypatch.undo()
    assert commands_path.read_text() == original, "custom commands were destroyed"


# --- recovery must actually repair, not just paper over ---------------------

def test_recovered_settings_are_written_back_to_disk(config_path):
    """Recovery used to happen in memory only, so the damaged file stayed
    damaged: every process start (tray, service, prefs) quarantined it again
    and showed the user the same alarming warning forever."""
    good = config.Settings()
    good.model = "tiny"
    config.save_config(good)
    second = config.Settings()
    second.model = "base"
    config.save_config(second)

    config_path.write_text("garbage {{{")
    config._config_cache = None
    config._config_mtime = 0.0

    config.load_config()

    on_disk = config_path.read_text()
    assert "garbage" not in on_disk, "the damaged file was left in place"
    assert "tiny" in on_disk, "the recovered settings were not persisted"


def test_a_damaged_config_is_quarantined_once_not_every_launch(config_path, monkeypatch):
    good = config.Settings()
    good.model = "tiny"
    config.save_config(good)
    second = config.Settings()
    second.model = "base"
    config.save_config(second)

    config_path.write_text("garbage {{{")

    # Distinct timestamps per launch — otherwise three quarantines inside the
    # same second collapse to one filename and the test proves nothing.
    stamps = iter(["20260101-000001", "20260101-000002", "20260101-000003"])
    real_strftime = config.time.strftime
    monkeypatch.setattr(config.time, "strftime",
                        lambda fmt, *a: next(stamps, "20260101-000009")
                        if fmt == "%Y%m%d-%H%M%S" else real_strftime(fmt, *a))

    for _ in range(3):  # three process starts
        config._config_cache = None
        config._config_mtime = 0.0
        loaded = config.load_config()

    assert loaded.model == "tiny"
    quarantined = list(config_path.parent.glob("config.toml.corrupt-*"))
    assert len(quarantined) == 1, f"re-quarantined on every launch: {len(quarantined)} copies"


def test_repairing_a_damaged_config_does_not_destroy_the_good_backup(config_path):
    """The backup is the only remaining copy of the user's real settings at
    that moment — overwriting it with the damaged file removes the safety net
    right when it is needed."""
    good = config.Settings()
    good.model = "tiny"
    config.save_config(good)
    second = config.Settings()
    second.model = "base"
    config.save_config(second)

    config_path.write_text("garbage {{{")
    config._config_cache = None
    config._config_mtime = 0.0
    config.load_config()

    backup = config_path.with_suffix(config_path.suffix + ".bak")
    contents = backup.read_text()
    assert "garbage" not in contents, "the good backup was overwritten with the damaged file"
    assert "tiny" in contents


def test_a_later_save_still_refreshes_the_backup_normally(config_path):
    """Repair must not permanently freeze the backup."""
    first = config.Settings()
    first.model = "tiny"
    config.save_config(first)

    config_path.write_text("garbage {{{")
    config._config_cache = None
    config._config_mtime = 0.0
    config.load_config()

    later = config.Settings()
    later.model = "medium"
    config.save_config(later)

    backup = config_path.with_suffix(config_path.suffix + ".bak")
    assert "garbage" not in backup.read_text()


def test_repair_failure_does_not_crash_the_app(config_path, monkeypatch):
    """A read-only config directory must not take the tray down."""
    good = config.Settings()
    good.model = "tiny"
    config.save_config(good)
    second = config.Settings()
    second.model = "base"
    config.save_config(second)
    config_path.write_text("garbage {{{")
    config._config_cache = None
    config._config_mtime = 0.0

    def refuse(*args, **kwargs):
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr(config, "write_text_atomic", refuse)

    loaded = config.load_config()  # must not raise

    assert loaded.model == "tiny", "in-memory recovery should still work"


# --- concurrent writers ------------------------------------------------------

def test_concurrent_saves_do_not_collide(tmp_path):
    """Three TalkType processes run at once — tray, dictation service and
    Preferences — and all of them save settings.

    A fixed temp filename meant they truncated each other's half-written file
    and then failed to rename it, raising FileNotFoundError out of save_config.
    """
    import threading

    path = str(tmp_path / "config.toml")
    errors = []

    def writer(tag):
        try:
            for _ in range(60):
                config.write_text_atomic(path, f'# {tag}\n' + f'model = "{tag}"\n' * 40)
        except Exception as e:
            errors.append(f"{tag}: {type(e).__name__}: {e}")

    threads = [threading.Thread(target=writer, args=(t,)) for t in ("alpha", "bravo", "charlie")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent saves raised: {errors[:3]}"

    # Whoever won, the file must hold exactly one complete version.
    written = [ln.split('"')[1] for ln in open(path).read().splitlines() if "model" in ln]
    assert written, "file ended up empty"
    assert len(set(written)) == 1, f"file interleaves several writers: {set(written)}"
    assert len(written) == 40, f"file is truncated: {len(written)} of 40 lines"


def test_no_temp_files_are_left_behind(tmp_path):
    path = str(tmp_path / "config.toml")
    config.write_text_atomic(path, "model = \"tiny\"\n")

    leftovers = [p.name for p in tmp_path.iterdir() if ".tmp" in p.name]
    assert not leftovers, f"temp files left behind: {leftovers}"

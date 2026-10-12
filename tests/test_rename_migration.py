"""Moving a TalkType install's folders to their TuxTalk names (0.15.0).

Nothing may ever be lost: settings and multi-GB models move by rename, the old
name is left as a symlink so an old copy still installed keeps working, and
when both names exist or the folder is on another disk nothing is overwritten.
"""
import os

from tuxtalk import rename_migration as rm


def _mk(p, f="x"):
    os.makedirs(p, exist_ok=True)
    with open(os.path.join(p, f), "w") as fh:
        fh.write("1")


def test_moves_old_folders_and_leaves_symlinks(tmp_path):
    h = str(tmp_path)
    _mk(f"{h}/.config/talktype", "config.toml")
    _mk(f"{h}/.local/share/TalkType/models", "m.bin")
    rm.migrate(home=h)
    assert os.path.isfile(f"{h}/.config/tuxtalk/config.toml")
    assert os.path.isfile(f"{h}/.local/share/TuxTalk/models/m.bin")
    assert os.path.islink(f"{h}/.config/talktype")
    assert os.path.realpath(f"{h}/.config/talktype") == os.path.realpath(f"{h}/.config/tuxtalk")


def test_dev_uses_dev_folders_only(tmp_path):
    h = str(tmp_path)
    _mk(f"{h}/.config/talktype-dev")
    _mk(f"{h}/.config/talktype")
    rm.migrate(home=h, dev=True)
    assert os.path.isdir(f"{h}/.config/tuxtalk-dev")
    assert not os.path.exists(f"{h}/.config/tuxtalk")      # production untouched


def test_both_exist_nothing_is_overwritten(tmp_path):
    h = str(tmp_path)
    _mk(f"{h}/.config/talktype", "old.toml")
    _mk(f"{h}/.config/tuxtalk", "new.toml")
    lines = rm.migrate(home=h)
    assert os.path.isfile(f"{h}/.config/talktype/old.toml")   # left alone
    assert os.path.isfile(f"{h}/.config/tuxtalk/new.toml")
    assert any("both exist" in line for line in lines)


def test_cross_device_falls_back_to_reverse_symlink(tmp_path, monkeypatch):
    h = str(tmp_path)
    _mk(f"{h}/.local/share/TalkType", "m.bin")

    def exdev(a, b):
        raise OSError(18, "Invalid cross-device link")
    monkeypatch.setattr(rm.os, "rename", exdev)
    rm.migrate(home=h)
    assert os.path.islink(f"{h}/.local/share/TuxTalk")
    assert os.path.isfile(f"{h}/.local/share/TuxTalk/m.bin")   # reached through the link
    assert os.path.isfile(f"{h}/.local/share/TalkType/m.bin")  # never copied, never moved


def test_second_run_does_nothing(tmp_path):
    h = str(tmp_path)
    _mk(f"{h}/.config/talktype")
    rm.migrate(home=h)
    assert rm.migrate(home=h) == []


def test_nothing_old_nothing_done(tmp_path):
    assert rm.migrate(home=str(tmp_path)) == []


def test_new_folder_holding_only_our_log_still_takes_the_old_one(tmp_path):
    # The logger creates ~/.config/tuxtalk to write tuxtalk.log the moment any
    # module loads. That must not count as "both exist", or settings look lost.
    h = str(tmp_path)
    _mk(f"{h}/.config/talktype", "config.toml")
    _mk(f"{h}/.config/tuxtalk", "tuxtalk.log")
    rm.migrate(home=h)
    assert os.path.isfile(f"{h}/.config/tuxtalk/config.toml")
    assert os.path.isfile(f"{h}/.config/tuxtalk/tuxtalk.log")
    assert os.path.islink(f"{h}/.config/talktype")


def test_startup_run_respects_the_off_switches(tmp_path):
    h = str(tmp_path)
    _mk(f"{h}/.config/talktype")
    assert rm.run_at_startup({"TUXTALK_NO_MIGRATE": "1"}, home=h) == []
    assert rm.run_at_startup({"FLATPAK_ID": "io.github.ronb1964.TuxTalk"}, home=h) == []
    assert os.path.isdir(f"{h}/.config/talktype") and not os.path.islink(f"{h}/.config/talktype")
    assert rm.run_at_startup({}, home=h) == ["moved .config/talktype to .config/tuxtalk"]


def test_startup_run_picks_dev_folders_from_dev_mode(tmp_path):
    h = str(tmp_path)
    _mk(f"{h}/.config/talktype-dev")
    rm.run_at_startup({"DEV_MODE": "1"}, home=h)
    assert os.path.isdir(f"{h}/.config/tuxtalk-dev")


def test_package_import_runs_the_migration_before_anything_else():
    import pathlib
    src = (pathlib.Path(rm.__file__).parent / "__init__.py").read_text()
    body = src.split('"""', 2)[2]                      # after the docstring
    first_code = [l for l in body.splitlines() if l.strip() and not l.startswith("#")]
    assert "rename_migration" in "\n".join(first_code[:4])


# --- the one-time "TalkType is now TuxTalk" notice ----------------------------
# Shown once by the tray when this start converted an old TalkType install, on
# whichever TuxTalk version that happens to be (users skip releases).

def test_converting_the_settings_asks_for_the_notice(tmp_path):
    h = str(tmp_path)
    _mk(f"{h}/.config/talktype", "config.toml")
    rm.migrate(home=h)
    assert rm.notice_pending(f"{h}/.config/tuxtalk")


def test_a_settings_folder_on_another_disk_asks_too(tmp_path, monkeypatch):
    h = str(tmp_path)
    _mk(f"{h}/.config/talktype", "config.toml")

    def exdev(a, b):
        raise OSError(18, "Invalid cross-device link")
    monkeypatch.setattr(rm.os, "rename", exdev)
    rm.migrate(home=h)
    assert rm.notice_pending(f"{h}/.config/tuxtalk")


def test_dev_settings_ask_in_the_dev_folder(tmp_path):
    h = str(tmp_path)
    _mk(f"{h}/.config/talktype-dev", "config.toml")
    rm.migrate(home=h, dev=True)
    assert rm.notice_pending(f"{h}/.config/tuxtalk-dev")


def test_a_new_install_never_sees_it(tmp_path):
    h = str(tmp_path)
    _mk(f"{h}/.config/tuxtalk", "config.toml")
    rm.migrate(home=h)
    assert not rm.notice_pending(f"{h}/.config/tuxtalk")


def test_only_models_moving_is_not_a_conversion(tmp_path):
    """Settings are what make it someone's install; a stray models folder alone
    is not worth a message."""
    h = str(tmp_path)
    _mk(f"{h}/.local/share/TalkType", "m.bin")
    rm.migrate(home=h)
    assert not rm.notice_pending(f"{h}/.config/tuxtalk")


def test_the_notice_is_shown_once(tmp_path):
    h = str(tmp_path)
    _mk(f"{h}/.config/talktype", "config.toml")
    rm.migrate(home=h)
    rm.notice_shown(f"{h}/.config/tuxtalk")
    assert not rm.notice_pending(f"{h}/.config/tuxtalk")
    rm.migrate(home=h)                                  # the next start
    assert not rm.notice_pending(f"{h}/.config/tuxtalk")


def test_the_tray_shows_it():
    import pathlib
    tray = (pathlib.Path(rm.__file__).parent / "tray.py").read_text()
    assert "rename_migration.notice_pending(" in tray
    assert "TalkType is now TuxTalk" in tray

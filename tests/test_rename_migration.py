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

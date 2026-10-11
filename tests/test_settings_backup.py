"""Settings backup: a file to move to another computer, and automatic copies
to undo a mistake (settings_backup.py)."""
import datetime
import json
import os
import zipfile

import pytest

from talktype import config, settings_backup as sb, stats


CONFIG_TEXT = '# TalkType config\nhotkey = "F8"\nmodel = "parakeet-v3"\ndevice = "vulkan"\n'
COMMANDS_TEXT = '[commands]\n"my email" = "ron@example.com"\n'


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Settings files in a temporary folder, every graphics device working."""
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "cfg" / "config.toml"))
    monkeypatch.setattr(config, "CUSTOM_COMMANDS_PATH", str(tmp_path / "cfg" / "custom_commands.toml"))
    monkeypatch.setattr(stats, "stats_path", lambda: str(tmp_path / "data" / "stats.json"))
    monkeypatch.setattr(sb, "_device_works_here", lambda device: True)
    (tmp_path / "cfg").mkdir()
    (tmp_path / "cfg" / "config.toml").write_text(CONFIG_TEXT)
    (tmp_path / "cfg" / "custom_commands.toml").write_text(COMMANDS_TEXT)
    return tmp_path


def read(path):
    with open(path) as f:
        return f.read()


def set_stats(days):
    stats._write(days)


def day(words):
    return {"dictations": 1, "words": words, "seconds": 1.0}


# --- the backup file ---------------------------------------------------------

def test_a_saved_backup_loads_back(home):
    set_stats({"2026-10-01": day(50)})
    dest = home / "TalkType-settings.zip"
    sb.write_backup(str(dest))

    # Everything changes after the backup...
    with open(config.CONFIG_PATH, "w") as f:
        f.write('hotkey = "F9"\n')
    with open(config.CUSTOM_COMMANDS_PATH, "w") as f:
        f.write("[commands]\n")

    backup = sb.read_backup(str(dest))
    assert backup.version
    sb.restore(backup)

    # ...and loading it brings it all back.
    assert read(config.CONFIG_PATH) == CONFIG_TEXT
    assert read(config.CUSTOM_COMMANDS_PATH) == COMMANDS_TEXT


def test_the_backup_is_a_plain_zip_with_the_settings_inside(home):
    dest = home / "b.zip"
    sb.write_backup(str(dest))
    with zipfile.ZipFile(dest) as z:
        names = set(z.namelist())
    assert {"config.toml", "custom_commands.toml", sb.MANIFEST} <= names


def test_a_backup_without_commands_still_works(home):
    os.remove(config.CUSTOM_COMMANDS_PATH)
    dest = home / "b.zip"
    sb.write_backup(str(dest))
    sb.restore(sb.read_backup(str(dest)))
    assert read(config.CONFIG_PATH) == CONFIG_TEXT


@pytest.mark.parametrize("make", [
    lambda p: p.write_text("not a zip at all"),
    lambda p: zipfile.ZipFile(p, "w").writestr("photo.jpg", b"x"),           # someone else's zip
    lambda p: _zip(p, {sb.MANIFEST: json.dumps({"app": "TalkType"})}),      # no settings inside
    lambda p: _zip(p, {sb.MANIFEST: json.dumps({"app": "TalkType"}),
                       "config.toml": 'hotkey = "F8'}),                      # damaged settings
])
def test_a_wrong_or_broken_file_is_turned_away(home, make):
    bad = home / "bad.zip"
    make(bad)
    with pytest.raises(sb.BackupError):
        sb.read_backup(str(bad))
    assert read(config.CONFIG_PATH) == CONFIG_TEXT      # nothing was touched


def _zip(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)


# --- a different computer ----------------------------------------------------

def test_a_device_this_computer_lacks_keeps_this_computers_device(home, monkeypatch):
    dest = home / "b.zip"
    with open(config.CONFIG_PATH, "w") as f:
        f.write(CONFIG_TEXT.replace('"vulkan"', '"cuda"'))
    sb.write_backup(str(dest))

    # The new computer: no NVIDIA card, currently on the processor.
    with open(config.CONFIG_PATH, "w") as f:
        f.write('hotkey = "F12"\ndevice = "cpu"\n')
    monkeypatch.setattr(sb, "_device_works_here", lambda device: device != "cuda")

    notes = sb.restore(sb.read_backup(str(dest)))
    text = read(config.CONFIG_PATH)
    assert 'device = "cpu"' in text and 'hotkey = "F8"' in text
    assert any("CUDA" in n for n in notes)


def test_a_device_that_works_here_comes_across(home):
    dest = home / "b.zip"
    sb.write_backup(str(dest))
    with open(config.CONFIG_PATH, "w") as f:
        f.write('device = "cpu"\n')
    assert sb.restore(sb.read_backup(str(dest))) == []
    assert 'device = "vulkan"' in read(config.CONFIG_PATH)


# --- stats -------------------------------------------------------------------

def test_loading_a_backup_merges_stats_and_keeps_the_higher_count(home):
    set_stats({"2026-10-01": day(50), "2026-10-02": day(10)})
    dest = home / "b.zip"
    sb.write_backup(str(dest))
    # Meanwhile this computer dictated more on the 2nd, and on a new day.
    set_stats({"2026-10-02": day(80), "2026-10-03": day(5)})

    sb.restore(sb.read_backup(str(dest)))
    days = stats.load()
    assert days["2026-10-01"]["words"] == 50     # from the backup
    assert days["2026-10-02"]["words"] == 80     # the higher one
    assert days["2026-10-03"]["words"] == 5      # kept


def test_restoring_an_automatic_copy_leaves_stats_alone(home):
    set_stats({"2026-10-01": day(50)})
    sb.snapshot_if_changed()
    set_stats({"2026-10-01": day(70)})
    sb.restore(sb.read_backup(sb.list_snapshots()[0].path))
    assert stats.load()["2026-10-01"]["words"] == 70


# --- automatic copies --------------------------------------------------------

def test_a_copy_is_taken_only_when_the_settings_changed(home):
    assert sb.snapshot_if_changed() is not None
    assert sb.snapshot_if_changed() is None             # same settings
    with open(config.CONFIG_PATH, "a") as f:
        f.write('language = "en"\n')
    assert sb.snapshot_if_changed() is not None
    assert len(sb.list_snapshots()) == 2


def test_only_the_last_ten_copies_are_kept(home, monkeypatch):
    clock = [datetime.datetime(2026, 10, 1, 8, 0, 0)]
    monkeypatch.setattr(sb, "_now", lambda: clock[0])
    for i in range(13):
        with open(config.CONFIG_PATH, "a") as f:
            f.write(f"# change {i}\n")
        sb.snapshot_if_changed()
        clock[0] += datetime.timedelta(minutes=1)
    copies = sb.list_snapshots()
    assert len(copies) == sb.KEEP == 10
    assert copies[0].when > copies[-1].when          # newest first
    assert "# change 12" in sb.read_backup(copies[0].path).files["config.toml"].decode()


def test_restoring_saves_the_current_settings_first_so_it_can_be_undone(home):
    sb.snapshot_if_changed()
    old = sb.list_snapshots()[0]
    with open(config.CONFIG_PATH, "w") as f:
        f.write('hotkey = "F9"\n')

    sb.restore(sb.read_backup(old.path))

    assert read(config.CONFIG_PATH) == CONFIG_TEXT
    newest = sb.list_snapshots()[0]
    assert sb.read_backup(newest.path).files["config.toml"] == b'hotkey = "F9"\n'


def test_no_settings_yet_means_no_copy(home):
    os.remove(config.CONFIG_PATH)
    assert sb.snapshot_if_changed() is None
    assert sb.list_snapshots() == []


def test_a_broken_copy_in_the_folder_is_skipped_not_fatal(home):
    sb.snapshot_if_changed()
    folder = sb.snapshots_dir()
    with open(os.path.join(folder, "settings-20261001-080000.zip"), "w") as f:
        f.write("junk")
    with open(os.path.join(folder, "notes.txt"), "w") as f:
        f.write("not a copy")
    assert len(sb.list_snapshots()) == 2           # listed by name; read on restore
    with open(config.CONFIG_PATH, "a") as f:
        f.write("# changed\n")
    assert sb.snapshot_if_changed() is not None    # the junk one didn't stop it


def test_copies_are_named_the_way_people_say_dates():
    now = datetime.datetime(2026, 10, 11, 9, 0)
    assert sb.when_label(datetime.datetime(2026, 10, 11, 8, 43), now) == "Today 8:43 AM"
    assert sb.when_label(datetime.datetime(2026, 10, 10, 21, 50), now) == "Yesterday 9:50 PM"
    assert sb.when_label(datetime.datetime(2026, 10, 2, 7, 5), now) == "Oct 2, 2026, 7:05 AM"


def test_last_saved_is_noted_and_doesnt_show_up_as_a_copy(home):
    assert sb.last_saved() is None
    sb.write_backup(str(home / "b.zip"))
    assert sb.last_saved() is not None
    assert sb.list_snapshots() == []

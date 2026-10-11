"""Back up and restore TalkType's settings.

Two uses:
- A backup file the user saves and loads from Preferences → Advanced, to move
  to another computer or keep through a reinstall. It holds the settings, the
  voice commands (Fix a Word saves its words there too) and the usage stats.
- Automatic copies, so a change or an update that went wrong can be undone.
  The tray takes one at startup when the settings changed since the last one,
  and keeps the last KEEP. They hold the settings and commands, not the
  stats: rolling back a setting mustn't take away today's word count.

Both are ordinary zip files with a small manifest, read by the same code.
Models and the CUDA / Vulkan files are not included: they are large and
download again by themselves.
"""
import datetime
import json
import os
import re
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass

from . import config, stats
from .logger import setup_logger

logger = setup_logger(__name__)

MANIFEST = "talktype-backup.json"
KEEP = 10                       # automatic copies kept
_SETTINGS = "config.toml"
_COMMANDS = "custom_commands.toml"
_STATS = "stats.json"
_COPY_NAME = re.compile(r"^settings-(\d{8}-\d{6})\.zip$")
_DEVICE_LINE = re.compile(r'^device\s*=.*$', re.MULTILINE)
_DEVICE_NAMES = {"cuda": "CUDA", "vulkan": "Vulkan"}


class BackupError(Exception):
    """A file that isn't a TalkType backup, or is damaged. The message is
    written for the user."""


@dataclass
class Backup:
    version: str                # the TalkType version that made it
    created: str                # ISO date and time
    files: dict                 # name in the zip -> bytes


@dataclass
class Snapshot:
    path: str
    when: datetime.datetime


def _now():
    return datetime.datetime.now()


def when_label(when, now=None):
    """'Today 8:43 AM', 'Yesterday 9:50 PM' or 'Oct 10, 2026, 9:50 PM'."""
    now = now or _now()
    clock = f"{when:%-I:%M %p}"
    if when.date() == now.date():
        return f"Today {clock}"
    if when.date() == now.date() - datetime.timedelta(days=1):
        return f"Yesterday {clock}"
    return f"{when:%b %-d, %Y}, {clock}"


def _setting_files():
    """The settings files by their name inside a backup. Read at call time,
    so the paths follow DEV_MODE and Flatpak like the rest of config."""
    return {_SETTINGS: config.CONFIG_PATH, _COMMANDS: config.CUSTOM_COMMANDS_PATH}


def snapshots_dir():
    """Where the automatic copies live, next to the settings."""
    return os.path.join(os.path.dirname(config.CONFIG_PATH), "backups")


def _read_bytes(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def _current_files(with_stats):
    files = {}
    for name, path in _setting_files().items():
        data = _read_bytes(path)
        if data is not None:
            files[name] = data
    if with_stats:
        data = _read_bytes(stats.stats_path())
        if data is not None:
            files[_STATS] = data
    return files


def _write_zip(path, files):
    """Write the zip beside *path* and rename it into place, so a full disk
    never leaves half a backup. Readable by the user only: commands can hold
    an email address or a signature."""
    from . import __version__
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    manifest = {"app": "TalkType", "version": __version__,
                "created": _now().isoformat(timespec="seconds")}
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".talktype-backup-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f, zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(MANIFEST, json.dumps(manifest, indent=1))
            for name, data in files.items():
                z.writestr(name, data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _last_saved_path():
    """When a backup file was last saved, for "Last saved:" in Preferences.
    Kept out of config.toml: Preferences writing a setting outside Apply/OK
    moves the baseline Apply compares against."""
    return os.path.join(snapshots_dir(), "last-saved-backup")


def last_saved():
    """When a backup file was last saved here, or None."""
    data = _read_bytes(_last_saved_path())
    try:
        return datetime.datetime.fromisoformat(data.decode().strip()) if data else None
    except (UnicodeDecodeError, ValueError):
        return None


def _folder_path():
    """The folder the user picked for backup files, kept beside the copies
    for the same reason as _last_saved_path."""
    return os.path.join(snapshots_dir(), "backup-folder")


def backup_folder():
    """The folder the user picked for backup files, or None when none was
    picked or it no longer exists (deleted, renamed, an unplugged drive)."""
    data = _read_bytes(_folder_path())
    try:
        folder = data.decode().strip() if data else ""
    except UnicodeDecodeError:
        return None
    return folder if folder and os.path.isdir(folder) else None


def set_backup_folder(folder):
    """Remember *folder* for Save Backup and Load Backup to open in."""
    os.makedirs(snapshots_dir(), mode=0o700, exist_ok=True)
    with open(_folder_path(), "w") as f:
        f.write(folder)


def write_backup(path):
    """Save the settings, commands and stats to the backup file *path*."""
    files = _current_files(with_stats=True)
    if _SETTINGS not in files:
        raise BackupError("There are no settings to back up yet.")
    _write_zip(path, files)
    try:
        os.makedirs(snapshots_dir(), mode=0o700, exist_ok=True)
        with open(_last_saved_path(), "w") as f:
            f.write(_now().isoformat(timespec="seconds"))
    except OSError as e:
        logger.warning(f"Could not note when the backup was saved: {e}")


def read_backup(path):
    """Open a backup file or automatic copy. Raises BackupError when it isn't
    one, or its settings are damaged, before anything is changed."""
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if MANIFEST not in names:
                raise BackupError("This file isn't a TalkType settings backup.")
            manifest = json.loads(z.read(MANIFEST))
            files = {n: z.read(n) for n in (_SETTINGS, _COMMANDS, _STATS) if n in names}
    except BackupError:
        raise
    except (zipfile.BadZipFile, OSError, ValueError, KeyError) as e:
        raise BackupError(f"This file isn't a TalkType settings backup, or it's damaged ({e}).")

    if not isinstance(manifest, dict) or manifest.get("app") != "TalkType":
        raise BackupError("This file isn't a TalkType settings backup.")
    if _SETTINGS not in files:
        raise BackupError("This backup has no settings in it.")
    for name in (_SETTINGS, _COMMANDS):
        if name in files:
            try:
                tomllib.loads(files[name].decode("utf-8"))
            except (UnicodeDecodeError, tomllib.TOMLDecodeError):
                raise BackupError(f"The settings in this backup are damaged ({name}).")
    return Backup(version=str(manifest.get("version", "")),
                  created=str(manifest.get("created", "")), files=files)


def _device_works_here(device):
    """Whether this computer can use *device*. CPU always can."""
    try:
        if device == "cuda":
            from .cuda_helper import detect_nvidia_gpu
            return bool(detect_nvidia_gpu())
        if device == "vulkan":
            from . import whisper_vulkan
            return whisper_vulkan.is_offered()
    except Exception as e:
        logger.warning(f"Could not check for {device}: {e}")
        return False
    return True


def _fit_device(text, notes):
    """The restored settings *text*, with the device swapped for this
    computer's own when this computer can't use the one in the backup (a
    backup from an NVIDIA computer, loaded on one without). The rest of the
    settings come across unchanged."""
    wanted = tomllib.loads(text).get("device")
    if not wanted or _device_works_here(wanted):
        return text
    current = _read_bytes(config.CONFIG_PATH)
    keep = "cpu"
    if current is not None:
        try:
            keep = tomllib.loads(current.decode("utf-8")).get("device") or "cpu"
        except (UnicodeDecodeError, tomllib.TOMLDecodeError):
            pass
    if not _device_works_here(keep):
        keep = "cpu"
    name = _DEVICE_NAMES.get(wanted, wanted)
    notes.append(f"The backup uses {name}, which this computer doesn't have, so the "
                 f"Device stays on {_DEVICE_NAMES.get(keep, 'CPU')}.")
    return _DEVICE_LINE.sub(f'device = "{keep}"', text, count=1)


def _merge_stats(data):
    """Add the backup's days to this computer's, keeping the higher count for
    a day both have, so loading a backup never loses any dictation."""
    try:
        theirs = json.loads(data).get("days", {})
    except (ValueError, AttributeError):
        return
    days = stats.load()
    for day, value in (theirs.items() if isinstance(theirs, dict) else []):
        try:
            datetime.date.fromisoformat(day)
        except (TypeError, ValueError):
            continue
        value = stats._clean_day(value)
        if day not in days or value["words"] > days[day]["words"]:
            days[day] = value
    stats._write(days)


def restore(backup):
    """Replace the settings and commands with *backup*'s, after saving the
    current ones as an automatic copy (so this can be undone). Stats, when
    the backup has them, are merged rather than replaced.

    Returns notes for the user, such as a device kept for this computer.
    """
    notes = []
    snapshot_if_changed()
    text = _fit_device(backup.files[_SETTINGS].decode("utf-8"), notes)
    config.write_text_atomic(config.CONFIG_PATH, text)
    if _COMMANDS in backup.files:
        config.write_text_atomic(config.CUSTOM_COMMANDS_PATH,
                                 backup.files[_COMMANDS].decode("utf-8"))
    if _STATS in backup.files:
        _merge_stats(backup.files[_STATS])
    logger.info(f"Settings restored from a backup made {backup.created} "
                f"by TalkType {backup.version}")
    return notes


def list_snapshots():
    """The automatic copies, newest first."""
    try:
        names = os.listdir(snapshots_dir())
    except FileNotFoundError:
        return []
    copies = []
    for name in names:
        match = _COPY_NAME.match(name)
        if match:
            when = datetime.datetime.strptime(match.group(1), "%Y%m%d-%H%M%S")
            copies.append(Snapshot(os.path.join(snapshots_dir(), name), when))
    return sorted(copies, key=lambda c: c.when, reverse=True)


def snapshot_if_changed():
    """Save the settings and commands as an automatic copy, unless they are
    the same as in the newest copy. Keeps the last KEEP. Returns the new
    copy's path, or None. Never raises: a missed copy mustn't stop TalkType
    starting."""
    try:
        files = _current_files(with_stats=False)
        if _SETTINGS not in files:
            return None
        copies = list_snapshots()
        if copies:
            try:
                if read_backup(copies[0].path).files == files:
                    return None
            except BackupError:
                pass                    # a damaged newest copy: take a fresh one
        # Named by the second, and a copy taken the same second as the last
        # one (a restore right after startup) must not overwrite it.
        when = _now()
        while True:
            path = os.path.join(snapshots_dir(), f"settings-{when:%Y%m%d-%H%M%S}.zip")
            if not os.path.exists(path):
                break
            when += datetime.timedelta(seconds=1)
        os.makedirs(snapshots_dir(), mode=0o700, exist_ok=True)
        _write_zip(path, files)
        for old in list_snapshots()[KEEP:]:
            os.remove(old.path)
        logger.info(f"Saved a copy of the settings: {os.path.basename(path)}")
        return path
    except Exception as e:
        logger.warning(f"Could not save a copy of the settings: {e}")
        return None

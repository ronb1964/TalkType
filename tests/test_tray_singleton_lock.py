"""The tray's single-instance lock.

Only a lock held by another tray means "already running". An error opening
the lock file (no runtime folder, no permission) must not make the tray exit
quietly, and a second tray must not wipe the first one's PID from the file.
"""

import os

import pytest

from tuxtalk import tray


@pytest.fixture
def lock_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tray, "_runtime_dir", lambda: str(tmp_path))
    saved = tray._tray_lockfile_handle
    yield tmp_path
    if tray._tray_lockfile_handle is not None and tray._tray_lockfile_handle is not saved:
        tray._tray_lockfile_handle.close()
    tray._tray_lockfile_handle = saved


def test_the_first_tray_takes_the_lock_and_records_its_pid(lock_dir):
    tray._acquire_tray_singleton()
    assert (lock_dir / "talktype-tray.lock").read_text() == str(os.getpid())


def test_a_second_tray_exits_and_leaves_the_pid_alone(lock_dir):
    tray._acquire_tray_singleton()
    first = tray._tray_lockfile_handle
    try:
        with pytest.raises(SystemExit) as exit_info:
            tray._acquire_tray_singleton()
        assert exit_info.value.code == 0
        assert (lock_dir / "talktype-tray.lock").read_text() == str(os.getpid())
    finally:
        tray._tray_lockfile_handle = first


def test_an_unusable_runtime_folder_is_not_reported_as_already_running(monkeypatch, tmp_path):
    monkeypatch.setattr(tray, "_runtime_dir", lambda: str(tmp_path / "missing"))
    tray._acquire_tray_singleton()   # must not raise SystemExit

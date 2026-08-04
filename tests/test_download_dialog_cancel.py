"""Closing the download window must stop the downloads it started.

Each task carries a threading.Event that the download loop checks between
chunks. The per-task Cancel button sets it; closing the window did not. The
dialog was destroyed, run() returned, and multi-gigabyte downloads carried on
in background threads writing to disk — invisible, uncancellable, and
reported to the caller as failures.
"""

import threading

from talktype.download_progress_dialog import DownloadTask, UnifiedDownloadDialog


def _task(name="CUDA Libraries"):
    return DownloadTask(name=name, description="test", size_text="~1.4GB",
                        download_func=lambda cb, ev: True)


def test_closing_the_window_cancels_unfinished_tasks():
    dlg = UnifiedDownloadDialog.__new__(UnifiedDownloadDialog)
    running, done = _task("CUDA Libraries"), _task("large-v3 AI Model")
    done.completed = True
    dlg.tasks = [running, done]

    dlg._cancel_unfinished_tasks()

    assert running.cancel_event.is_set(), "download kept running after the window closed"


def test_closing_the_window_leaves_finished_tasks_alone():
    """A completed download must not be marked cancelled on the way out."""
    dlg = UnifiedDownloadDialog.__new__(UnifiedDownloadDialog)
    done = _task()
    done.completed = True
    done.success = True
    dlg.tasks = [done]

    dlg._cancel_unfinished_tasks()

    assert not done.cancelled
    assert done.success is True

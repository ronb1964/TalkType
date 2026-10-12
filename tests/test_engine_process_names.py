"""An engine's parent is recognised under the new name (TuxTalk, 0.15.0).

kill_orphans() kills any graphics or AI engine whose parent does not look like
our app. After the rename the parent runs as `python -m tuxtalk.app` or from
TuxTalk.AppImage, so a check for "talktype" alone would kill live engines.
"""
import subprocess
import sys
import time

from tuxtalk import engine_process

# Not the project venv: its path contains "TalkType", which would make every
# test process look like ours.
_PY = "/usr/bin/python3" if __import__("os").path.exists("/usr/bin/python3") else sys.executable


def _sleeper(*marker):
    p = subprocess.Popen([_PY, "-c", "import time; time.sleep(30)", *marker])
    # /proc/<pid>/cmdline reads empty for a moment after spawn; wait it out.
    for _ in range(200):
        with open(f"/proc/{p.pid}/cmdline", "rb") as f:
            if f.read():
                break
        time.sleep(0.005)
    return p


def test_tuxtalk_parent_is_ours():
    p = _sleeper("-m", "tuxtalk.app")
    try:
        assert engine_process.is_talktype_process(p.pid)
    finally:
        p.kill()


def test_old_talktype_parent_still_counts():
    p = _sleeper("/home/u/AppImages/TalkType.AppImage")
    try:
        assert engine_process.is_talktype_process(p.pid)
    finally:
        p.kill()


def test_unrelated_process_is_not_ours():
    p = _sleeper("something-else")
    try:
        assert not engine_process.is_talktype_process(p.pid)
    finally:
        p.kill()

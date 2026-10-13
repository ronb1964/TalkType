"""fresh-start-for-testing.sh stops TuxTalk's own programs and nothing else.

It force-kills whatever survives its first stop, so a loose pattern would also
kill an editor with a TuxTalk file open or a `tail -f` on the log.
"""
import pathlib
import re

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "fresh-start-for-testing.sh"
APP_PAT = re.search(r"^APP_PAT='(.*)'$", SCRIPT.read_text(), re.M).group(1)


@pytest.mark.parametrize("cmdline", [
    "/home/u/Projects/TalkType/.venv/bin/python -m tuxtalk.tray",
    "/home/u/Projects/TalkType/.venv/bin/python -m tuxtalk.app",
    "/usr/bin/python3 -m tuxtalk.parakeet_gpu_worker",
    "/opt/talktype/usr/bin/python3 -m tuxtalk.tray tray",
    "./TuxTalk-v0.15.0-x86_64.AppImage",
    "/home/u/AppImages/TalkType.AppImage",
    "/tmp/.mount_TuxTalAb12/usr/bin/ydotoold",
    "/home/u/.local/share/TuxTalk/whisper-vulkan/1.9.4/x/whisper-server --port 9",
    "/home/u/.local/share/TuxTalk-dev/ai/llama-b1/llama-server -m q.gguf",
])
def test_app_programs_are_stopped(cmdline):
    assert re.search(APP_PAT, cmdline)


@pytest.mark.parametrize("cmdline", [
    "kate /home/u/Projects/TalkType/src/tuxtalk/app.py",
    "tail -f /tmp/tuxtalk-output.log",
    "less /home/u/.config/tuxtalk/tuxtalk.log",
    "bash -c ./fresh-start-for-testing.sh | tee /tmp/tuxtalk-fresh.log",
    "/usr/bin/python3 -m pytest tests",
])
def test_other_programs_are_left_alone(cmdline):
    assert not re.search(APP_PAT, cmdline)


def test_the_check_uses_the_same_pattern():
    text = SCRIPT.read_text()
    assert 'pkill -f "tuxtalk|talktype"' not in text
    assert text.count('pgrep -f -- "$APP_PAT"') == 2

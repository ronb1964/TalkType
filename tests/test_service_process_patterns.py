"""Killing the dictation service must never kill the tray that owns it.

Process identification was hand-rolled at six call sites with four different
patterns, and they disagreed:

  * app.py's D-Bus quit handler used a bare "talktype", which matches the tray,
    Preferences, and any shell command that merely mentions the project path.
    Measured live during a review: six matching processes, including the dev
    tray the user runs all day.
  * tray.py and welcome_dialog.py used "-m talktype", which matches
    "-m talktype.tray" — the tray's own command line. It has never actually run:
    pkill reads a pattern starting with a dash as an option and aborts. The
    obvious repair (adding "--") would make the tray SIGKILL itself, so the
    pattern has to be narrowed rather than merely made parseable.
  * "bin/dictate" is a prefix of "bin/dictate-tray", which is the only launcher
    the shipped AppImage actually contains.

One helper now owns the patterns, and these tests pin the property that matters:
every pattern hits the service, and none of them hits the tray.

pkill -f matches an extended regular expression against the whole command line,
so the patterns are checked here with re.search.
"""

import pathlib
import re

import pytest

from talktype import service_launcher

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Real command lines, as they appear in /proc. The AppImage ones were taken
# from an extracted v0.7.2: usr/bin/dictate-tray execs "python3 -m talktype.tray",
# and usr/bin/dictate does not ship at all, so the service runs as the module.
SERVICE_COMMAND_LINES = [
    "/home/ron/Projects/TalkType/.venv/bin/python -m talktype.app",
    "/tmp/.mount_TalkTyabc/usr/bin/python3 -m talktype.app",
    "/opt/talktype/usr/bin/dictate",
    "/opt/talktype/usr/bin/dictate --verbose",
]

# Anything here being killed is a bug. The tray is the parent process: killing
# it takes down the menu, the D-Bus service and the user's only way to quit.
MUST_SURVIVE_COMMAND_LINES = [
    "/home/ron/Projects/TalkType/.venv/bin/python -m talktype.tray",
    "/tmp/.mount_TalkTyabc/usr/bin/python3 -m talktype.tray",
    "/tmp/.mount_TalkTyabc/usr/bin/dictate-tray",
    "/tmp/.mount_TalkTyabc/usr/bin/python3 -m talktype.prefs",
    "/bin/bash -c cd /home/ron/Projects/TalkType && ./build-release.sh",
    "node /home/ron/.local/share/talktype-notes/index.js",
]


def _matches(pattern, command_line):
    return re.search(pattern, command_line) is not None


class TestThePatternsHitTheService:
    @pytest.mark.parametrize("command_line", SERVICE_COMMAND_LINES)
    def test_every_service_command_line_is_matched(self, command_line):
        assert any(
            _matches(p, command_line)
            for p in service_launcher.SERVICE_KILL_PATTERNS
        ), f"nothing would kill the service running as {command_line!r}"


class TestThePatternsSpareEverythingElse:
    @pytest.mark.parametrize("command_line", MUST_SURVIVE_COMMAND_LINES)
    def test_no_pattern_matches(self, command_line):
        hits = [
            p for p in service_launcher.SERVICE_KILL_PATTERNS
            if _matches(p, command_line)
        ]
        assert hits == [], f"{hits} would kill {command_line!r}"

    def test_the_tray_is_spared_specifically(self):
        """The regression that mattered: '-m talktype' matches '-m talktype.tray'."""
        tray = "/usr/bin/python3 -m talktype.tray"
        assert not any(
            _matches(p, tray) for p in service_launcher.SERVICE_KILL_PATTERNS
        )

    def test_dictate_tray_is_spared(self):
        """'bin/dictate' is a prefix of the only launcher the AppImage ships."""
        assert not any(
            _matches(p, "/tmp/.mount_x/usr/bin/dictate-tray")
            for p in service_launcher.SERVICE_KILL_PATTERNS
        )


class TestStopDictationService:
    def test_it_runs_pkill_for_every_pattern(self, monkeypatch):
        calls = []
        monkeypatch.setattr(service_launcher.subprocess, "run",
                            lambda argv, **kw: calls.append(argv))

        service_launcher.stop_dictation_service()

        used = [c[-1] for c in calls]
        assert used == list(service_launcher.SERVICE_KILL_PATTERNS)
        assert all("-9" not in c for c in calls), "a normal stop must not SIGKILL"

    def test_force_uses_sigkill(self, monkeypatch):
        calls = []
        monkeypatch.setattr(service_launcher.subprocess, "run",
                            lambda argv, **kw: calls.append(argv))

        service_launcher.stop_dictation_service(force=True)

        assert all("-9" in c for c in calls)

    def test_every_call_is_bounded(self, monkeypatch):
        """A wedged pkill must not hang the GTK thread that called it."""
        seen = []
        monkeypatch.setattr(service_launcher.subprocess, "run",
                            lambda argv, **kw: seen.append(kw.get("timeout")))

        service_launcher.stop_dictation_service()

        assert all(t is not None for t in seen)

    def test_a_failing_pkill_does_not_propagate(self, monkeypatch):
        """Quit and onboarding both call this; neither may die on it."""
        def boom(argv, **kw):
            raise OSError("pkill not found")

        monkeypatch.setattr(service_launcher.subprocess, "run", boom)

        service_launcher.stop_dictation_service()  # must not raise


class TestNobodyHandRollsItAnyMore:
    def test_only_the_helper_shells_out_to_pkill(self):
        """Six call sites with four patterns is how they drifted apart."""
        offenders = []
        for path in (ROOT / "src" / "talktype").glob("*.py"):
            if path.name == "service_launcher.py":
                continue
            if '"pkill"' in path.read_text() or "'pkill'" in path.read_text():
                offenders.append(path.name)

        assert offenders == [], (
            f"{offenders} run pkill directly; use "
            f"service_launcher.stop_dictation_service() so the patterns stay "
            f"in one place"
        )

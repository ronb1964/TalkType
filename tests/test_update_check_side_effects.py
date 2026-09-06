"""Three cleanup fixes that share a theme: a slow operation holding stale state.

1. The daily update check snapshotted the whole Settings object, spent up to
   ~30s on a network call, then wrote all 36 fields back just to record a
   timestamp. Anything the user changed in Preferences during that window was
   silently reverted. config.py is otherwise careful — atomic writes, fsync,
   backups, a refusal to save after a failed read — but atomic writing prevents
   corruption, not clobbering by a stale snapshot.

2. Installing a .deb/.rpm through pkexec had no timeout, so a package lock
   (routine on Ubuntu with unattended-upgrades) hung the update dialog forever
   with no cancel path. The repair has to be careful: the child runs as root,
   a user process cannot kill it, and killing a package manager mid-transaction
   is far worse than waiting. So the wait is bounded and the process is left
   alone to finish.

3. wtype had no timeout at all, though the ydotool branch directly above it
   kills and reaps after 20s. On a compositor that stalls, dictation froze with
   no text and no error.
"""

import subprocess

import pytest

from talktype import config as config_module


class TestRecordingTheUpdateCheck:
    def test_it_does_not_carry_other_settings_along(self, monkeypatch):
        """The bug: a setting changed during the network call is reverted."""
        saved = {}

        # What the tray held before its ~30s network call.
        stale = config_module.Settings(model="small", auto_period=True)
        # What the user changed to in Preferences while it was running.
        on_disk = config_module.Settings(model="large-v3", auto_period=False)

        monkeypatch.setattr(config_module, "load_config", lambda: on_disk)
        monkeypatch.setattr(config_module, "save_config",
                            lambda s: saved.update(model=s.model,
                                                   auto_period=s.auto_period,
                                                   last_update_check=s.last_update_check))

        config_module.record_update_check("2026-09-05", _stale=stale)

        assert saved["model"] == "large-v3", "the user's model choice was reverted"
        assert saved["auto_period"] is False
        assert saved["last_update_check"] == "2026-09-05"

    def test_a_failed_read_does_not_write(self, monkeypatch):
        """Losing a timestamp beats overwriting real settings with defaults."""
        def unreadable():
            raise OSError("config unreadable")

        monkeypatch.setattr(config_module, "load_config", unreadable)
        monkeypatch.setattr(config_module, "save_config",
                            lambda s: pytest.fail("must not save after a failed read"))

        config_module.record_update_check("2026-09-05")  # must not raise


class TestPackageInstallIsBounded:
    def _checker(self):
        from talktype import update_checker
        return update_checker

    def test_a_hung_package_manager_returns_instead_of_blocking(self, monkeypatch):
        uc = self._checker()

        class HungProc:
            def communicate(self, timeout=None):
                raise subprocess.TimeoutExpired(cmd="pkexec", timeout=timeout)
            def kill(self):
                pytest.fail("a package manager must never be killed mid-transaction")

        monkeypatch.setattr(uc, "package_install_argv",
                            lambda t, p: ["pkexec", "apt", "install", "-y", p])
        monkeypatch.setattr(uc.subprocess, "Popen", lambda *a, **k: HungProc())

        ok, message = uc.install_package_update("/tmp/x.deb", "deb")

        assert ok is False
        assert "still" in message.lower() or "taking" in message.lower()

    def test_a_normal_install_still_succeeds(self, monkeypatch):
        uc = self._checker()

        class GoodProc:
            returncode = 0
            def communicate(self, timeout=None):
                return ("", "")

        monkeypatch.setattr(uc, "package_install_argv",
                            lambda t, p: ["pkexec", "apt", "install", "-y", p])
        monkeypatch.setattr(uc.subprocess, "Popen", lambda *a, **k: GoodProc())

        ok, _ = uc.install_package_update("/tmp/x.deb", "deb")

        assert ok is True

    def test_a_cancelled_authorization_is_still_reported(self, monkeypatch):
        uc = self._checker()

        class CancelledProc:
            returncode = 126
            def communicate(self, timeout=None):
                return ("", "")

        monkeypatch.setattr(uc, "package_install_argv",
                            lambda t, p: ["pkexec", "apt", "install", "-y", p])
        monkeypatch.setattr(uc.subprocess, "Popen", lambda *a, **k: CancelledProc())

        ok, message = uc.install_package_update("/tmp/x.deb", "deb")

        assert ok is False
        assert "cancel" in message.lower()


class TestWtypeIsBounded:
    def test_a_stalled_wtype_is_killed_and_reported(self, monkeypatch):
        from talktype import app

        monkeypatch.setattr(app, "_which", lambda name: name == "wtype")

        killed = []

        class HungProc:
            returncode = None
            def communicate(self, timeout=None):
                if not killed:
                    raise subprocess.TimeoutExpired(cmd="wtype", timeout=timeout)
                return (b"", b"")
            def kill(self):
                killed.append(True)

        monkeypatch.setattr(app.subprocess, "Popen", lambda *a, **k: HungProc())

        assert app._type_text_raw("hello") is False
        assert killed, "a hung wtype must be killed, not left typing later"

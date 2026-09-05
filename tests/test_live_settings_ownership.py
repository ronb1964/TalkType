"""One owner for the config-change signal, and no snapshots of live settings.

Two separate bugs, one shape: a setting Preferences reports as "applied without
restart" that the running service never actually picks up.

1. The change signal was being consumed twice. _config_file_changed() is
   edge-triggered — it compares mtime against a module global and returns True
   once per change. The evdev loop calls _service_tick() first and then runs its
   own copy of the same check to rebind hold_key/toggle_key/mode. Once
   _service_tick gained the recheck (for Backend B, which runs no evdev loop),
   it consumed every change first, so the inline block always saw False and the
   loop kept the hotkey it started with. Changing your hotkey did nothing until
   a restart, on every non-Flatpak build.

   The fix makes _service_tick the single detector and hands the result back to
   whoever needs to rebind.

2. _ServiceState snapshotted the auto-timeout at construction. _reload_live_settings
   refreshes cfg in place, but the snapshot never moved, so switching the timeout
   off left the service still exiting on it (and switching it on did nothing).
"""

import types

import pytest

from talktype import app


def _idle(monkeypatch):
    """A service that is running but not recording."""
    app._cmd_start_recording.clear()
    app._cmd_stop_recording.clear()
    monkeypatch.setattr(app.state, "is_recording", False, raising=False)


def _cfg(**overrides):
    base = dict(auto_timeout_enabled=False, auto_timeout_minutes=5, notify=False)
    base.update(overrides)
    return types.SimpleNamespace(**base)


class TestChangeSignalHasOneOwner:
    def test_tick_hands_back_the_reloaded_settings(self, monkeypatch):
        """The evdev loop rebinds its hotkey locals from this return value.

        Without it the loop has to re-detect the change itself, and the
        detector is edge-triggered — the tick already consumed it.
        """
        _idle(monkeypatch)
        live = app.LiveSettings(
            hold_key=60, toggle_key=None, vc_hotkey_str="",
            voice_cmds_combo=None, voice_cmds_main_key=None, mode="hold",
        )
        monkeypatch.setattr(app, "_config_file_changed", lambda: True)
        monkeypatch.setattr(app, "_reload_live_settings", lambda cfg, ind: live)

        cfg = _cfg()
        assert app._service_tick(cfg, None, app._ServiceState(cfg)) is live

    def test_tick_hands_back_nothing_when_the_config_is_unchanged(self, monkeypatch):
        _idle(monkeypatch)
        monkeypatch.setattr(app, "_config_file_changed", lambda: False)

        cfg = _cfg()
        assert app._service_tick(cfg, None, app._ServiceState(cfg)) is None

    def test_a_new_hotkey_survives_the_tick(self, monkeypatch):
        """End to end: the change is detected once and the new key comes back.

        This is the regression. The old code detected it inside the tick,
        discarded the result, and left the caller to detect it a second time —
        which could never succeed.
        """
        _idle(monkeypatch)
        monkeypatch.setattr(app, "_config_file_changed", lambda: True)
        monkeypatch.setattr(app, "load_config", lambda: _cfg(
            hotkey="F9", toggle_hotkey="", voice_commands_hotkey="", mode="hold",
            typing_delay=12, log_transcripts=False,
        ))

        cfg = _cfg(hotkey="F8", toggle_hotkey="", voice_commands_hotkey="",
                   mode="hold", typing_delay=12, log_transcripts=False)
        live = app._service_tick(cfg, None, app._ServiceState(cfg))

        assert live is not None, "the tick must return what it reloaded"
        assert live.hold_key == app._keycode_from_name("F9")


class TestAutoTimeoutIsLive:
    def test_disabling_the_timeout_takes_effect_without_a_restart(self, monkeypatch):
        """Untick 'auto-timeout' and the service must stop exiting on it."""
        _idle(monkeypatch)
        cfg = _cfg(auto_timeout_enabled=True, auto_timeout_minutes=5)
        svc = app._ServiceState(cfg)

        # What _reload_live_settings does: update cfg in place.
        cfg.auto_timeout_enabled = False

        assert svc.timeout_enabled is False

    def test_enabling_the_timeout_takes_effect_without_a_restart(self, monkeypatch):
        _idle(monkeypatch)
        cfg = _cfg(auto_timeout_enabled=False, auto_timeout_minutes=1)
        svc = app._ServiceState(cfg)

        cfg.auto_timeout_enabled = True

        assert svc.timeout_enabled is True
        assert svc.timeout_seconds == 60

    def test_a_shortened_timeout_takes_effect_without_a_restart(self, monkeypatch):
        _idle(monkeypatch)
        cfg = _cfg(auto_timeout_enabled=True, auto_timeout_minutes=30)
        svc = app._ServiceState(cfg)

        cfg.auto_timeout_minutes = 2

        assert svc.timeout_minutes == 2
        assert svc.timeout_seconds == 120

    def test_a_disabled_timeout_does_not_shut_the_service_down(self, monkeypatch):
        """The user-visible failure: 'disabled' and it exits anyway."""
        _idle(monkeypatch)
        monkeypatch.setattr(app, "_config_file_changed", lambda: False)
        cfg = _cfg(auto_timeout_enabled=True, auto_timeout_minutes=5)
        svc = app._ServiceState(cfg)
        svc.last_activity = 0.0  # idle since the epoch

        cfg.auto_timeout_enabled = False

        app._service_tick(cfg, None, svc)  # must not raise SystemExit

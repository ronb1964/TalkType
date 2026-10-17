"""Turn other sounds down while dictating (audio_duck.py), with a fake pactl.

Asked for in Handy (#2008, "must have"); Superwhisper ("Muffle", Oct 2) and
Vocalinux 0.18 (Oct 6) added it. It reaches what pausing can't: calls,
games, apps without media keys.
"""
import json
import subprocess

from tuxtalk import audio_duck

OWN_PID = 4242


class FakePactl:
    """Sink inputs with per-channel volumes; answers list and set-volume."""

    def __init__(self, streams):
        # index -> {"pid":, "volumes": [...], "mute":}
        self.streams = streams
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd[1:])
        args = cmd[1:]
        if args[:4] == ["-f", "json", "list", "sink-inputs"]:
            out = [{"index": i, "mute": s.get("mute", False),
                    "properties": {"application.process.id": str(s["pid"])},
                    "volume": {f"ch{n}": {"value": v} for n, v in enumerate(s["volumes"])}}
                   for i, s in self.streams.items()]
            return subprocess.CompletedProcess(cmd, 0, json.dumps(out), "")
        if args[0] == "set-sink-input-volume":
            index = int(args[1])
            if index not in self.streams:
                return subprocess.CompletedProcess(cmd, 1, "", "No such entity")
            self.streams[index]["volumes"] = [int(v) for v in args[2:]]
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 1, "", "unknown")


def _ducker(tmp_path, pactl):
    return audio_duck.AudioDucker(run=pactl, own_pid=OWN_PID, state_path=str(tmp_path / "ducked.json"))


def test_other_apps_go_down_and_come_back(tmp_path):
    pactl = FakePactl({7: {"pid": 100, "volumes": [65536, 65536]},
                       9: {"pid": 200, "volumes": [40000]}})
    d = _ducker(tmp_path, pactl)
    d._duck_now()
    assert pactl.streams[7]["volumes"] == [16384, 16384]
    assert pactl.streams[9]["volumes"] == [10000]
    assert (tmp_path / "ducked.json").exists()       # for a crash mid-dictation
    d._restore_now()
    assert pactl.streams[7]["volumes"] == [65536, 65536]
    assert pactl.streams[9]["volumes"] == [40000]
    assert not (tmp_path / "ducked.json").exists()


def test_tuxtalks_own_beeps_and_muted_streams_are_left_alone(tmp_path):
    pactl = FakePactl({1: {"pid": OWN_PID, "volumes": [65536]},
                       2: {"pid": 300, "volumes": [65536], "mute": True}})
    d = _ducker(tmp_path, pactl)
    d._duck_now()
    assert pactl.streams[1]["volumes"] == [65536]
    assert pactl.streams[2]["volumes"] == [65536]
    assert not any(c[0] == "set-sink-input-volume" for c in pactl.calls)


def test_a_volume_the_user_changed_meanwhile_is_kept(tmp_path):
    pactl = FakePactl({7: {"pid": 100, "volumes": [65536]}})
    d = _ducker(tmp_path, pactl)
    d._duck_now()
    pactl.streams[7]["volumes"] = [30000]          # turned up by hand during dictation
    d._restore_now()
    assert pactl.streams[7]["volumes"] == [30000]


def test_a_stream_that_ended_is_skipped(tmp_path):
    pactl = FakePactl({7: {"pid": 100, "volumes": [65536]}})
    d = _ducker(tmp_path, pactl)
    d._duck_now()
    del pactl.streams[7]
    d._restore_now()                                # no error


def test_left_over_volumes_are_put_back_at_the_next_start(tmp_path):
    pactl = FakePactl({7: {"pid": 100, "volumes": [65536]}})
    d = _ducker(tmp_path, pactl)
    d._duck_now()                                   # ...and the service dies here
    assert pactl.streams[7]["volumes"] == [16384]
    restored = audio_duck.restore_left_over(run=pactl, state_path=str(tmp_path / "ducked.json"))
    assert restored == 1
    assert pactl.streams[7]["volumes"] == [65536]
    assert not (tmp_path / "ducked.json").exists()


def test_no_pactl_is_not_an_error(tmp_path):
    def missing(cmd, **kw):
        raise FileNotFoundError("pactl")
    d = _ducker(tmp_path, missing)
    d._duck_now()
    d._restore_now()
    assert audio_duck.restore_left_over(run=missing, state_path=str(tmp_path / "none.json")) == 0


def test_setting_is_off_by_default_and_live():
    from tuxtalk import config
    assert config.Settings().duck_audio is False
    assert "duck_audio" in config.LIVE_APPLIED_KEYS


def test_recording_hooks_duck_and_restore(monkeypatch):
    from tuxtalk import app
    calls = []

    class Ducker:
        def duck(self):
            calls.append("duck")

        def restore(self):
            calls.append("restore")
    monkeypatch.setattr(app, "_duck_audio", True)
    monkeypatch.setattr(app, "_pause_media", False)
    monkeypatch.setattr(app, "_audio_ducker", Ducker())
    app._pause_media_players()
    app._resume_media_players()
    assert calls == ["duck", "restore"]
    # Switched off mid-recording: still restored.
    monkeypatch.setattr(app, "_duck_audio", False)
    app._resume_media_players()
    assert calls[-1] == "restore"

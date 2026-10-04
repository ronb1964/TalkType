"""Hands-free auto-stop: the silence detector, on synthetic audio.

Audio is built from quiet room noise and louder "speech" (noise plus a tone),
fed in 20 ms blocks the way the microphone callback delivers it.
"""
import time

import numpy as np
import pytest

from talktype.silence import SilenceDetector

SR = 16000
BLOCK = 320   # 20 ms
rng = np.random.default_rng(0)


def noise(seconds, level=60.0):
    return (rng.normal(0, level, int(seconds * SR))).astype(np.int16)


def speech(seconds, level=3000.0, noise_level=60.0):
    """Syllables: 180 ms of voice, then a 70 ms gap where only the room is
    heard, like real speech (a detector must not rely on a gapless tone)."""
    t = np.arange(int(seconds * SR)) / SR
    voiced = (t % 0.25) < 0.18
    tone = np.sin(2 * np.pi * 220 * t) * level * voiced
    return (tone + rng.normal(0, noise_level, t.size)).astype(np.int16)


def run(audio, silence_seconds=1.5):
    """Feed audio in blocks; return (seconds at which it fired or None, detector)."""
    det = SilenceDetector(silence_seconds, SR)
    for i in range(0, len(audio), BLOCK):
        if det.feed(audio[i:i + BLOCK].tobytes()):
            return (i + BLOCK) / SR, det
    return None, det


def test_stops_after_the_speaker_goes_quiet():
    audio = np.concatenate([noise(0.5), speech(2.0), noise(3.0)])
    at, _ = run(audio, 1.5)
    assert at == pytest.approx(0.5 + 2.0 + 1.5, abs=0.1)


def test_never_stops_before_the_speaker_starts():
    """A slow start (long silence before talking) is not "done"."""
    at, _ = run(np.concatenate([noise(6.0), speech(1.0)]), 1.5)
    assert at is None


def test_a_click_or_cough_does_not_count_as_talking():
    audio = np.concatenate([noise(1.0), speech(0.1), noise(4.0)])
    at, _ = run(audio, 1.5)
    assert at is None


def test_a_thinking_pause_shorter_than_the_setting_does_not_stop_it():
    audio = np.concatenate([noise(0.3), speech(1.0), noise(1.2), speech(1.0), noise(3.0)])
    at, _ = run(audio, 1.5)
    assert at == pytest.approx(0.3 + 1.0 + 1.2 + 1.0 + 1.5, abs=0.1)


def test_works_in_a_noisier_room():
    """Background noise well above a quiet room's still reads as silence."""
    audio = np.concatenate([noise(0.5, 400), speech(2.0, 4000, 400), noise(3.0, 400)])
    at, _ = run(audio, 1.5)
    assert at == pytest.approx(4.0, abs=0.1)


def test_fires_only_once():
    audio = np.concatenate([speech(1.0), noise(3.0), speech(1.0), noise(3.0)])
    det = SilenceDetector(1.0, SR)
    fired = sum(det.feed(audio[i:i + BLOCK].tobytes()) for i in range(0, len(audio), BLOCK))
    assert fired == 1


def test_trims_only_the_measured_silent_tail():
    _, det = run(np.concatenate([speech(2.0), noise(3.0)]), 2.0)
    assert det.fired
    # 2.0 s of silence measured, 0.3 s kept for the last word's decay.
    assert det.tail_to_trim() == pytest.approx(int(1.7 * SR), abs=BLOCK)


def test_nothing_is_trimmed_unless_it_fired():
    _, det = run(np.concatenate([speech(2.0), noise(0.5)]), 2.0)
    assert not det.fired and det.tail_to_trim() == 0


def test_talking_instantly_with_no_quiet_gaps_still_counts_as_speech():
    """Even speech whose gaps never get quiet is recognised when it starts at once."""
    t = np.arange(int(2.0 * SR)) / SR
    gapless = (np.sin(2 * np.pi * 220 * t) * 3000).astype(np.int16)
    at, _ = run(np.concatenate([gapless, noise(3.0)]), 1.5)
    assert at == pytest.approx(3.5, abs=0.1)


def test_talking_the_instant_recording_starts_still_counts_as_speech():
    """The first block cannot be taken as the room's background noise."""
    at, _ = run(np.concatenate([speech(2.0), noise(3.0)]), 1.5)
    assert at == pytest.approx(3.5, abs=0.1)


# --- Wiring into the service -------------------------------------------------

def _start(monkeypatch, from_toggle=True, seconds=1.0):
    from talktype import app
    monkeypatch.setattr(app, "_auto_stop_seconds", seconds)
    monkeypatch.setattr(app, "_open_input_stream", lambda idx: setattr(app.state, "recording_samplerate", SR))
    monkeypatch.setattr(app, "_beep", lambda *a, **k: None)
    monkeypatch.setattr(app, "_notify_tray_recording_state", lambda *a: None)
    monkeypatch.setattr(app, "recording_indicator", None, raising=False)
    assert app.start_recording(False, False, 0, from_toggle=from_toggle)
    app._cmd_stop_recording.clear()
    return app


def _speak_then_go_quiet(app, quiet_seconds=3.0):
    audio = np.concatenate([speech(1.0), noise(quiet_seconds)])
    for i in range(0, len(audio), BLOCK):
        app._sd_callback(audio[i:i + BLOCK].reshape(-1, 1), BLOCK, None, None)


def test_a_single_tap_is_a_plain_toggle_however_long_the_pause(monkeypatch):
    app = _start(monkeypatch)
    assert app.state.silence is None
    _speak_then_go_quiet(app, quiet_seconds=8.0)
    assert not app._cmd_stop_recording.is_set()
    app.state.is_recording = False


def test_a_double_tap_switches_to_hands_free_and_it_stops_itself(monkeypatch):
    app = _start(monkeypatch)
    assert app._toggle_pressed_while_recording(beeps_on=False) is True   # 2nd tap: keep going
    assert app.state.silence is not None
    _speak_then_go_quiet(app)
    assert app._cmd_stop_recording.is_set()
    app._cmd_stop_recording.clear()
    app.state.is_recording = False


def test_a_slow_second_tap_is_a_normal_stop(monkeypatch):
    app = _start(monkeypatch)
    app.state.toggle_started_at -= app.DOUBLE_TAP_S + 0.1
    assert app._toggle_pressed_while_recording(beeps_on=False) is False
    assert app.state.silence is None
    app.state.is_recording = False


def test_a_third_tap_after_a_double_tap_stops(monkeypatch):
    app = _start(monkeypatch)
    assert app._toggle_pressed_while_recording(beeps_on=False) is True
    assert app._toggle_pressed_while_recording(beeps_on=False) is False
    app.state.is_recording = False


def test_double_tap_does_nothing_special_with_the_option_off(monkeypatch):
    app = _start(monkeypatch, seconds=0.0)
    assert app._toggle_pressed_while_recording(beeps_on=False) is False
    app.state.is_recording = False


def test_a_hold_recording_cannot_become_hands_free(monkeypatch):
    app = _start(monkeypatch, from_toggle=False)
    assert app._toggle_pressed_while_recording(beeps_on=False) is False
    _speak_then_go_quiet(app)
    assert not app._cmd_stop_recording.is_set()
    app.state.is_recording = False


def test_the_silent_tail_is_trimmed_and_speech_is_kept(monkeypatch):
    from talktype import app
    monkeypatch.setattr(app, "_stop_stream_safely", lambda: None)
    monkeypatch.setattr(app, "_notify_tray_recording_state", lambda *a: None)
    monkeypatch.setattr(app, "recording_indicator", None, raising=False)
    det = SilenceDetector(2.0, SR)
    talk, quiet = speech(1.0), noise(2.4)   # 2.4 s: blocks keep arriving after it fires
    speech_blocks = [talk[i:i + BLOCK].tobytes() for i in range(0, len(talk), BLOCK)]
    silent_blocks = [quiet[i:i + BLOCK].tobytes() for i in range(0, len(quiet), BLOCK)]
    for blk in speech_blocks + silent_blocks:
        det.feed(blk)
    assert det.fired
    app.state.silence = det
    app.state.frames = speech_blocks + silent_blocks
    app.state.is_recording = True
    app.state.was_cancelled = False
    app.state.press_t0 = time.time() - 5   # held well past MIN_HOLD_MS
    frames, _ = app._finish_capture(False, False)
    kept_s = sum(len(f) // 2 for f in frames) / SR
    # 1 s of speech (its last syllable gap counts as silence) + 0.3 s kept.
    assert 1.1 <= kept_s <= 1.4
    assert frames[:50] == speech_blocks  # every speech block untouched
    assert app.state.silence is None


def test_auto_stop_settings_apply_without_a_restart():
    from talktype.config import LIVE_APPLIED_KEYS
    assert {"auto_stop_silence", "auto_stop_seconds"} <= LIVE_APPLIED_KEYS


def test_setting_follows_config(monkeypatch):
    from types import SimpleNamespace
    from talktype import app
    monkeypatch.setattr(app, "_ai_engine", None)
    app._apply_cleanup_settings(SimpleNamespace(auto_stop_silence=True, auto_stop_seconds=3.0))
    assert app._auto_stop_seconds == 3.0
    app._apply_cleanup_settings(SimpleNamespace(auto_stop_silence=False, auto_stop_seconds=3.0))
    assert app._auto_stop_seconds == 0.0


# --- an accidental tap of the hold key ------------------------------------------
# A tap just over the minimum hold time records a fraction of a second of room
# noise and the key's click, and Parakeet can "hear" a word in that: "Thank
# you." was typed into Konsole while testing 0.14.0 (2026-10-03).

from talktype.silence import is_speechless_tap  # noqa: E402


def f32(int16_audio):
    return int16_audio.astype(np.float32) / 32768.0


def click(seconds=0.25, noise_level=60.0):
    """Room noise with a key click: 10 ms, loud."""
    audio = noise(seconds, noise_level).astype(np.float64)
    start = int(0.05 * SR)
    audio[start:start + 160] += rng.normal(0, 6000, 160)
    return np.clip(audio, -32768, 32767).astype(np.int16)


def test_a_tap_with_only_room_noise_has_no_speech():
    assert is_speechless_tap(f32(noise(0.25)), SR)


def test_a_tap_with_a_key_click_has_no_speech():
    assert is_speechless_tap(f32(click()), SR)


def test_a_tap_on_a_noisy_desk_mic_has_no_speech():
    """Shaped like real taps from a Sennheiser Profile: a noisy background
    and a key thump about 4x louder for 40 ms. The first version of this check
    (1.5x) let such taps through, and Parakeet typed "Yeah." for them."""
    audio = noise(0.3, 100).astype(np.float64)
    start = int(0.02 * SR)
    audio[start:start + 640] += rng.normal(0, 380, 640)
    assert is_speechless_tap(f32(np.clip(audio, -32768, 32767).astype(np.int16)), SR)


def test_a_quick_word_is_kept():
    word = np.concatenate([noise(0.08), speech(0.3), noise(0.07)])
    assert not is_speechless_tap(f32(word), SR)


def test_a_quick_quiet_word_is_kept_too():
    """Judged against the clip's own background, not a fixed loudness, so a
    quiet microphone isn't mistaken for silence."""
    word = np.concatenate([noise(0.08, 15), speech(0.3, level=250, noise_level=15),
                           noise(0.07, 15)])
    assert not is_speechless_tap(f32(word), SR)


def test_a_word_that_fills_the_whole_tap_is_kept():
    """Real speech has no neat gaps; with a 4x ratio this dropped 224 of 510
    real half-second clips, because the clip's quietest blocks were speech."""
    t = np.arange(int(0.45 * SR)) / SR
    voice = np.sin(2 * np.pi * 180 * t) * (2000 + 800 * np.sin(2 * np.pi * 4 * t))
    assert not is_speechless_tap(f32((voice + rng.normal(0, 60, t.size)).astype(np.int16)), SR)


def test_anything_longer_than_a_tap_is_never_judged():
    """Long recordings go to the engine as always, silent or not."""
    assert not is_speechless_tap(f32(noise(1.0)), SR)


def test_the_service_skips_a_speechless_tap(monkeypatch):
    from talktype import app
    monkeypatch.setattr(app, "_transcribe_audio",
                        lambda *a: pytest.fail("a speechless tap was transcribed"))
    app._transcribe_and_inject([click().tobytes()], SR, False, False, False)

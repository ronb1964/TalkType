"""Chunked dictation: the pause detector and chunk worker on synthetic audio,
and the app's chunk pipeline with a fake engine and fake typing.

Audio is built like test_silence.py: quiet room noise and louder "speech"
(noise plus a tone, with syllable gaps), fed in 20 ms blocks.
"""
import threading
import time

import numpy as np
import pytest

SR = 16000
BLOCK = 320   # 20 ms at 16 kHz
rng = np.random.default_rng(1)


def noise(seconds, level=60.0, sr=SR):
    return (rng.normal(0, level, int(seconds * sr))).astype(np.int16)


def speech(seconds, level=3000.0, noise_level=60.0, sr=SR):
    """Syllables: 180 ms of voice, then a 70 ms gap where only the room is heard."""
    t = np.arange(int(seconds * sr)) / sr
    voiced = (t % 0.25) < 0.18
    tone = np.sin(2 * np.pi * 220 * t) * level * voiced
    return (tone + rng.normal(0, noise_level, t.size)).astype(np.int16)


def blocks(audio, block=BLOCK):
    for i in range(0, len(audio), block):
        yield audio[i:i + block]


# --- the shared noise floor ---------------------------------------------------

def test_noise_floor_tells_room_from_voice():
    from tuxtalk.silence import NoiseFloor, block_rms
    floor = NoiseFloor()
    for b in blocks(noise(1.0)):
        rms, dur = block_rms(b.tobytes(), SR)
        assert floor.update(rms, dur) is False
    loud = speech(0.18)[:BLOCK]
    rms, dur = block_rms(loud.tobytes(), SR)
    assert floor.update(rms, dur) is True


def test_block_rms_of_an_empty_block():
    from tuxtalk.silence import block_rms
    assert block_rms(b"", SR) == (0.0, 0.0)


# --- the pause detector ------------------------------------------------------

def run_pauses(audio, pause=0.8, sr=SR, block=BLOCK):
    """Feed audio in blocks; return (times in s at which a boundary fired, detector)."""
    from tuxtalk.chunking import PauseDetector
    det = PauseDetector(pause, sr)
    fired = []
    for i in range(0, len(audio), block):
        if det.feed(audio[i:i + block].tobytes()):
            fired.append((i + block) / sr)
    return fired, det


def test_a_pause_after_speech_is_a_boundary():
    fired, det = run_pauses(np.concatenate([speech(1.0), noise(1.5)]))
    assert len(fired) == 1
    # The last voiced syllable ends at ~0.93 s, so 0.8 s of quiet is reached by ~1.75 s.
    assert 1.6 <= fired[0] <= 1.9
    assert det.last_pause >= 0.8


def test_a_short_pause_is_not_a_boundary():
    fired, _ = run_pauses(np.concatenate([speech(1.0), noise(0.5), speech(1.0), noise(0.2)]))
    assert fired == []


def test_it_rearms_after_each_boundary():
    audio = np.concatenate([speech(1.0), noise(1.0), speech(1.0), noise(1.0)])
    fired, _ = run_pauses(audio)
    assert len(fired) == 2


def test_a_cough_alone_is_not_a_boundary():
    fired, _ = run_pauses(np.concatenate([noise(0.5), speech(0.2), noise(2.0)]))
    assert fired == []


def test_long_silence_gives_one_boundary():
    fired, _ = run_pauses(np.concatenate([speech(1.0), noise(10.0)]))
    assert len(fired) == 1


def test_cough_in_a_long_silence_is_forgotten():
    """A cough after a boundary, then more silence, then another cough: the two
    coughs must not add up to 'enough speech' and cut a chunk of room noise."""
    audio = np.concatenate([speech(1.0), noise(1.0), speech(0.2), noise(3.0),
                            speech(0.2), noise(3.0)])
    fired, _ = run_pauses(audio)
    assert len(fired) == 1


def test_tail_keeps_the_last_words_decay():
    from tuxtalk.chunking import TAIL_KEEP_S
    fired, det = run_pauses(np.concatenate([speech(1.0), noise(1.5)]))
    assert fired
    expected = int((det.last_pause - TAIL_KEEP_S) * SR)
    assert abs(det.tail_samples() - expected) <= BLOCK


def test_works_at_48k():
    sr, block = 48000, 960
    audio = np.concatenate([speech(1.0, sr=sr), noise(1.5, sr=sr)])
    fired, _ = run_pauses(audio, sr=sr, block=block)
    assert len(fired) == 1
    assert 1.6 <= fired[0] <= 1.9


# --- the chunk worker --------------------------------------------------------

def test_worker_runs_jobs_in_order():
    from tuxtalk.chunking import ChunkWorker
    w = ChunkWorker()
    done = []
    for i in range(5):
        w.submit(lambda i=i: (time.sleep(0.01 * (5 - i)), done.append(i)))
    assert w.drain(5)
    assert done == [0, 1, 2, 3, 4]


def test_a_failing_chunk_does_not_stop_the_next():
    from tuxtalk.chunking import ChunkWorker
    w = ChunkWorker()
    done = []

    def boom():
        raise RuntimeError("engine fell over")

    w.submit(lambda: done.append(1))
    w.submit(boom)
    w.submit(lambda: done.append(3))
    assert w.drain(5)
    assert done == [1, 3]


def test_drain_waits_for_the_job_in_progress():
    from tuxtalk.chunking import ChunkWorker
    w = ChunkWorker()
    w.submit(lambda: time.sleep(0.5))
    assert w.drain(0.1) is False
    assert w.drain(5) is True


def test_drain_with_nothing_queued_returns_at_once():
    from tuxtalk.chunking import ChunkWorker
    assert ChunkWorker().drain(0.01) is True


def test_jobs_run_holding_the_lock():
    from tuxtalk.chunking import ChunkWorker
    lock = threading.Lock()
    w = ChunkWorker(lock)
    seen = []
    w.submit(lambda: seen.append(lock.locked()))
    assert w.drain(5)
    assert seen == [True]


# --- settings ----------------------------------------------------------------

def test_chunk_settings_default_off():
    from tuxtalk.config import Settings
    s = Settings()
    assert s.chunked_dictation is False
    assert s.chunk_pause_seconds == 0.8


@pytest.mark.parametrize("value,ok", [(0.8, True), (0.3, True), (3.0, True),
                                      (0.2, False), (3.5, False)])
def test_chunk_pause_range(value, ok):
    from tuxtalk import config
    problems = config._validation_problems(config.Settings(chunk_pause_seconds=value))
    flagged = any(key == "chunk_pause_seconds" for key, _msg in problems)
    assert flagged is (not ok)


def test_chunk_settings_apply_without_a_restart():
    from tuxtalk.config import LIVE_APPLIED_KEYS
    assert {"chunked_dictation", "chunk_pause_seconds"} <= LIVE_APPLIED_KEYS


def test_chunk_setting_follows_config(monkeypatch):
    from types import SimpleNamespace
    from tuxtalk import app
    monkeypatch.setattr(app, "_ai_engine", None)
    on = SimpleNamespace(chunked_dictation=True, chunk_pause_seconds=1.0)
    app._apply_cleanup_settings(on)
    assert app._chunk_pause_seconds == 1.0
    assert app._chunk_cfg is on
    app._apply_cleanup_settings(SimpleNamespace(chunked_dictation=False, chunk_pause_seconds=1.0))
    assert app._chunk_pause_seconds == 0.0


def test_chunk_pause_stays_below_auto_stop(monkeypatch):
    from types import SimpleNamespace
    from tuxtalk import app
    monkeypatch.setattr(app, "_ai_engine", None)
    app._apply_cleanup_settings(SimpleNamespace(
        chunked_dictation=True, chunk_pause_seconds=1.5,
        auto_stop_silence=True, auto_stop_seconds=1.0))
    assert app._chunk_pause_seconds == pytest.approx(0.8)
    app._apply_cleanup_settings(SimpleNamespace(chunked_dictation=False))


# --- chunk roles in the pipeline ---------------------------------------------

@pytest.fixture
def pipeline(monkeypatch):
    """A fake engine and fake typing around the real _transcribe_and_inject.
    texts: what the engine 'hears', one per call. Returns (texts, typed, beeps)."""
    from tuxtalk import app, history
    texts, typed, beeps = [], [], []
    monkeypatch.setattr(app, "_transcribe_audio", lambda audio, lang: texts.pop(0))
    monkeypatch.setattr(app, "_inject_text",
                        lambda text, mode, t0, one_block=False: (typed.append(text), "ok")[1])
    monkeypatch.setattr(app, "_beep", lambda enabled, *tone: beeps.append(tone))
    monkeypatch.setattr(app, "_notify", lambda *a, **k: None)
    monkeypatch.setattr(app, "_query_focused_window_class", lambda: None)
    monkeypatch.setattr(app, "_adapt_to_app", False)
    monkeypatch.setattr(app, "_usage_stats", False)
    monkeypatch.setattr(history, "add_entry", lambda text: None)
    monkeypatch.setattr(app.state, "continue_mid_sentence", False)
    return texts, typed, beeps


def frames_of(audio):
    return [audio.tobytes()]


def call(frames, role, auto_period=False):
    from tuxtalk import app
    app._transcribe_and_inject(frames, SR, True, True, False, None, True, auto_period,
                               "type", chunk_role=role)


def test_middle_chunk_types_without_the_ready_beep(pipeline):
    from tuxtalk import app
    texts, typed, beeps = pipeline
    texts.append("we meet")
    call(frames_of(speech(1.0)), "middle")
    assert [t.strip() for t in typed] == ["We meet"]
    assert app.READY_BEEP not in beeps


def test_middle_chunk_without_final_punctuation_continues_the_sentence(pipeline):
    from tuxtalk import app
    texts, typed, _ = pipeline
    texts.extend(["we meet", "at three"])
    call(frames_of(speech(1.0)), "middle")
    assert app.state.continue_mid_sentence is True
    call(frames_of(speech(1.0)), "last")
    assert typed[1].strip().startswith("at three")


def test_silent_middle_chunk_is_dropped_without_a_sound(pipeline):
    texts, typed, beeps = pipeline
    call(frames_of(noise(0.4)), "middle")
    assert typed == [] and beeps == []


def test_last_chunk_with_no_speech_still_beeps_ready(pipeline):
    from tuxtalk import app
    _, typed, beeps = pipeline
    call(frames_of(noise(0.4)), "last")
    assert typed == []
    assert beeps == [app.READY_BEEP]


def test_last_chunk_with_no_audio_beeps_ready(pipeline):
    from tuxtalk import app
    _, typed, beeps = pipeline
    call([], "last")
    assert typed == [] and beeps == [app.READY_BEEP]


def test_whole_dictation_is_unchanged(pipeline):
    """chunk_role=None: today's behaviour, a silent tap gets the cancel beep."""
    from tuxtalk import app
    _, typed, beeps = pipeline
    call(frames_of(noise(0.4)), None)
    assert typed == [] and beeps == [app.CANCEL_BEEP]

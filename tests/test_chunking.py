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

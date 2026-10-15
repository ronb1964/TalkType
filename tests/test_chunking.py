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

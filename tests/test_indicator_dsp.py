"""Spectrum DSP for the 'bars' indicator style.

Per-band background subtraction: each band learns its own quiet baseline and
shows only energy above it, so a steady tone (AC hum, mic DC offset) fades to
nothing while speech transients pop. Pure numpy — tested without a display.
"""
import numpy as np

from talktype.indicator_dsp import SpectrumProcessor

SR = 16000


def _tone(freq, n, amp=0.3):
    t = np.arange(n) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_output_shape_and_range():
    sp = SpectrumProcessor(sample_rate=SR, bins=20)
    out = sp.process(_tone(1000, 1600))
    assert out.shape == (20,)
    assert np.all(out >= 0.0) and np.all(out <= 1.0)


def test_steady_tone_is_subtracted_to_near_zero():
    sp = SpectrumProcessor(sample_rate=SR, bins=20)
    tone = _tone(1000, 1600)
    last = None
    for _ in range(400):
        last = sp.process(tone)
    assert last.max() < 0.15, "a steady tone should decay toward zero"


def test_silence_is_zero():
    sp = SpectrumProcessor(sample_rate=SR, bins=20)
    out = sp.process(np.zeros(1600, dtype=np.float32))
    assert out.max() < 1e-6


def test_steady_dc_offset_is_removed():
    """A constant (pure DC) signal must not show as spectrum energy — the mean
    is subtracted before the FFT, so once the ring is filled it reads as zero.
    This is the fix for the low bar that used to sit pinned high."""
    sp = SpectrumProcessor(sample_rate=SR, bins=20)
    const = np.full(1600, 0.8, dtype=np.float32)
    out = None
    for _ in range(6):        # fill the ring buffer with the constant
        out = sp.process(const)
    assert out.max() < 0.05, "steady DC offset must be removed, not shown"

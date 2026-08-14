"""Frequency-band DSP for the recording indicator's 'bars' style.

Per-band background subtraction: each band learns its own quiet baseline and
shows only energy above it, so a steady tone (an air conditioner, the
microphone's DC offset) is subtracted to nothing while speech transients pop.
Without this, low-frequency energy dominates every frame and pins the low bars
while everything else ramps down from the left.

Pure numpy — no GTK — so it is unit-tested without a display.
See docs/superpowers/specs/2026-08-14-recording-indicator-styles-design.md.
"""
import numpy as np


class SpectrumProcessor:
    def __init__(self, sample_rate=16000, ring_size=5600, bins=20,
                 freq_lo=110, freq_hi=4200):
        self.bins = bins
        self._ring = np.zeros(ring_size, dtype=np.float32)
        self._window = np.hanning(ring_size).astype(np.float32)
        freqs = np.fft.rfftfreq(ring_size, 1.0 / sample_rate)
        edges = np.linspace(freq_lo, freq_hi, bins + 1)
        # Which rfft bins fall in each display band. Everything below freq_lo
        # (DC offset, AC hum, room rumble — below speech) is excluded entirely.
        self._slices = [np.where((freqs >= edges[i]) & (freqs < edges[i + 1]))[0]
                        for i in range(bins)]
        self._floor = np.zeros(bins, dtype=np.float32)
        self._ceil = np.full(bins, 1e-4, dtype=np.float32)

    def process(self, samples):
        """Return `bins` floats in 0..1 for the most recent audio."""
        samples = np.asarray(samples, dtype=np.float32)
        n = len(samples)
        if n >= len(self._ring):
            self._ring = samples[-len(self._ring):].copy()
        else:
            self._ring = np.concatenate([self._ring[n:], samples])

        # Subtract the mean before the FFT so bin 0 (DC) stops dominating.
        win = (self._ring - self._ring.mean()) * self._window
        mag = np.abs(np.fft.rfft(win))
        raw = np.array([mag[idx].mean() if len(idx) else 0.0 for idx in self._slices])
        raw = np.log1p(raw * 4.0)

        # floor drops instantly to a new quiet level, creeps up slowly toward
        # steady energy — so a constant tone is learned as baseline.
        below = raw < self._floor
        self._floor[below] = raw[below]
        self._floor[~below] += (raw[~below] - self._floor[~below]) * 0.02
        residual = np.maximum(0.0, raw - self._floor)

        # ceiling: fast attack, slow decay, giving each band full range.
        up = residual > self._ceil
        self._ceil[up] = residual[up]
        self._ceil[~up] *= 0.99
        return np.clip(residual / (self._ceil + 1e-4), 0.0, 1.0).astype(np.float32)

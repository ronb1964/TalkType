#!/usr/bin/env python3
"""Step B of the Flatpak GPU spike: run a REAL Whisper transcription on the GPU
from inside the sandbox, and prove it did NOT fall back to CPU.

Decodes the bundled 16 kHz mono WAV with the stdlib `wave` module (so we don't
depend on PyAV for I/O) and hands faster-whisper a float32 numpy array. The CUDA
toolkit libs (cudart/cublas/cudnn) come from the host's downloaded set via
LD_LIBRARY_PATH; libcuda comes from the NVIDIA GL extension (proven in Step A).
"""
import os
import sys
import wave

import numpy as np


def _load_wav_f32(path):
    with wave.open(path, "rb") as wf:
        assert wf.getnchannels() == 1, "expected mono"
        assert wf.getframerate() == 16000, "expected 16 kHz"
        assert wf.getsampwidth() == 2, "expected 16-bit PCM"
        pcm = wf.readframes(wf.getnframes())
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def main():
    import ctranslate2

    dev_count = ctranslate2.get_cuda_device_count()
    print(f"ctranslate2.get_cuda_device_count() = {dev_count}")
    if dev_count < 1:
        print("RESULT: FAIL — ctranslate2 sees no CUDA device in the sandbox")
        return 2

    from faster_whisper import WhisperModel

    # Loads on GPU; float16 is the compute type the app uses on cuda. If CUDA were
    # unusable this raises (we do NOT pass a CPU fallback), so a clean load already
    # means the GPU path works.
    model = WhisperModel("base", device="cuda", compute_type="float16",
                         local_files_only=True)
    print("WhisperModel loaded on device=cuda (no CPU fallback requested)")

    audio = _load_wav_f32("/app/share/test.wav")
    segments, info = model.transcribe(audio, language="en", vad_filter=False,
                                      beam_size=5)
    text = " ".join(s.text.strip() for s in segments).strip()
    print(f"TRANSCRIPT: {text!r}")

    if text:
        print("RESULT: PASS — GPU transcription ran inside the Flatpak sandbox")
        return 0
    print("RESULT: FAIL — transcription returned empty text")
    return 3


if __name__ == "__main__":
    sys.exit(main())

"""
Parakeet on the graphics chip, through the Vulkan engine.

Used when the device is "Vulkan (any GPU)" and the model is Parakeet. On an
RTX 4070 Super it transcribed 66 s of speech in 0.17 s, against 2.15 s for the
processor engine (parakeet_engine.py), with no loss of accuracy (2026-10-03).

whisper.cpp has no Parakeet server, so the model runs in a helper process of
TalkType's own (parakeet_gpu_worker.py) that the dictation service starts and
talks to over pipes. Like the other engines (engine_process.py) it dies with
the service.

If the helper fails twice in a row, transcription moves to the processor
engine for the rest of the session, when that model is downloaded. TalkType
keeps both downloads for exactly this.
"""
import json
import os
import select
import struct
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import engine_process
from .logger import setup_logger
from .parakeet_engine import PARAKEET_MODEL, load_parakeet_model

logger = setup_logger(__name__)

SAMPLE_RATE = 16000
START_TIMEOUT = 180          # the very first run on a chip compiles shaders (8 s on an RTX 4070 Super)
MIN_SAMPLES = SAMPLE_RATE    # shorter recordings are padded with silence to one second


class ParakeetGpuModel:
    """Parakeet running on graphics chip *device_index* in a helper process.

    Offers recognize(), like the processor's ParakeetModel, so the dictation
    code treats the two the same."""

    def __init__(self, device_index, threads=None, command=None):
        from . import whisper_vulkan as wv
        self.device_index = device_index
        threads = threads or max(1, (os.cpu_count() or 2) // 2)
        self._command = command or [
            sys.executable, "-m", "talktype.parakeet_gpu_worker",
            wv._engine_dir(), wv.model_path(PARAKEET_MODEL), str(device_index), str(threads)]
        self._proc = None
        self._stderr = None
        self._cpu = None
        self._lock = threading.Lock()
        # The helper dies with the thread that started it (PR_SET_PDEATHSIG
        # is per thread), and a restart can happen on a short-lived dictation
        # thread (the Flatpak build makes one per dictation). So every start
        # goes through this one thread, which lives as long as the model.
        self._launcher = ThreadPoolExecutor(max_workers=1, thread_name_prefix="parakeet-gpu")
        self._start()

    # --- the helper process ---------------------------------------------------

    def _start(self):
        self._stop()
        # The engine's own messages go to a temporary file: kept out of the way,
        # but there to explain a helper that dies while starting.
        self._stderr = tempfile.TemporaryFile()
        self._proc = self._launcher.submit(
            subprocess.Popen, self._command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self._stderr, preexec_fn=engine_process.set_parent_death_signal).result()
        logger.info(f"Parakeet graphics helper starting (pid {self._proc.pid}, "
                    f"device {self.device_index})")
        reply = self._read_reply(START_TIMEOUT)
        if not reply.get("ready"):
            self._stop()
            raise RuntimeError(reply.get("error") or "the helper did not start")
        logger.info("Parakeet graphics helper ready")

    def _engine_messages(self):
        """The last lines the engine printed, to explain a failure."""
        try:
            self._stderr.seek(0)
            lines = self._stderr.read().decode(errors="replace").strip().splitlines()
            return " | ".join(lines[-3:])
        except Exception:
            return ""

    def _read_reply(self, timeout):
        out = self._proc.stdout
        ready, _, _ = select.select([out], [], [], timeout)
        if not ready:
            raise RuntimeError(f"the helper did not answer within {timeout:.0f} s")
        line = out.readline()
        if not line:
            raise RuntimeError(f"the helper stopped ({self._engine_messages() or 'no message'})")
        return json.loads(line)

    def _stop(self):
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        if self._stderr is not None:
            self._stderr.close()
            self._stderr = None

    def _recognize_on_gpu(self, audio):
        if self._proc is None or self._proc.poll() is not None:
            logger.warning("Parakeet graphics helper had stopped; starting it again")
            self._start()
        self._proc.stdin.write(struct.pack("<I", len(audio)) + audio.tobytes())
        self._proc.stdin.flush()
        reply = self._read_reply(60 + len(audio) / SAMPLE_RATE)
        if "error" in reply:
            raise RuntimeError(reply["error"])
        return reply.get("text", "").strip()

    # --- what the dictation service calls ------------------------------------

    def recognize(self, audio_f32) -> str:
        """Transcribe 16 kHz mono float32 audio and return the text."""
        audio = np.ascontiguousarray(audio_f32, dtype="<f4")
        if len(audio) < MIN_SAMPLES:
            audio = np.pad(audio, (0, MIN_SAMPLES - len(audio)))
        with self._lock:
            if self._cpu is not None:
                return self._cpu.recognize(audio)
            for attempt in (1, 2):
                try:
                    return self._recognize_on_gpu(audio)
                except Exception as e:
                    logger.warning(f"Parakeet on the graphics chip failed (try {attempt}): {e}")
                    self._stop()
            # Twice in a row: something is wrong with the chip or its driver.
            # Use the processor for the rest of this session.
            try:
                self._cpu = load_parakeet_model()
            except Exception as e:
                raise RuntimeError("Parakeet failed on the graphics chip, and its processor "
                                   f"version isn't available ({e})") from e
            logger.warning("Parakeet moved to the processor for the rest of this session")
            return self._cpu.recognize(audio)

    def close(self):
        with self._lock:
            self._stop()
        self._launcher.shutdown(wait=False)

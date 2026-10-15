"""Chunked dictation: type each phrase at the pause after it.

While a recording runs, PauseDetector listens for the speaker pausing. At each
pause the audio so far is handed to ChunkWorker, which transcribes and types it
while the speaker goes on talking. The result is finished phrases appearing at
natural pauses, never words appearing and changing mid-sentence (upstream's
"live text", which it decided against).

Off unless chunked_dictation is set in config.toml; see app._arm_chunker.
"""
import queue
import threading
import time

from .logger import setup_logger
from .silence import NoiseFloor, block_rms

logger = setup_logger(__name__)

# Talking needed before a pause can end a chunk: a cough or a click is shorter.
MIN_SPEECH_S = 0.3
# Silence kept at the end of a chunk, so the last word's decay is never cut.
TAIL_KEEP_S = 0.3
# The quietest level (int16 RMS, about -58 dBFS) that can count as speech.
# Auto-stop's 300 is far too high for a dynamic mic in a quiet room: measured
# on a Beyerdynamic M 70 PRO X into a MiniFuse 2, the room sat at 1-6 and
# speech at 50-600, so no pause was ever found. Erring low is safe here: noise
# taken for speech only costs a cut, it never cuts mid-word.
MIN_SPEECH_RMS = 40.0


class PauseDetector:
    """Feed it the recording's audio blocks; it says when a chunk ends.

    Unlike silence.SilenceDetector (which ends the recording once), this fires
    at every pause and then waits for new speech before it can fire again.
    """

    def __init__(self, pause_seconds: float, sample_rate: int):
        self.pause_seconds = float(pause_seconds)
        self.sample_rate = int(sample_rate)
        self._floor = NoiseFloor(MIN_SPEECH_RMS)
        self.speech_time = 0.0
        self.silence_time = 0.0
        self.last_pause = 0.0
        self._tail_s = 0.0

    def feed(self, block) -> bool:
        """Add one block of int16 samples. True when the speaker has paused for
        pause_seconds after talking for at least MIN_SPEECH_S."""
        rms, duration = block_rms(block, self.sample_rate)
        if duration == 0:
            return False
        if self._floor.update(rms, duration):
            self.speech_time += duration
            self.silence_time = 0.0
            return False
        self.silence_time += duration
        if self.silence_time < self.pause_seconds:
            return False
        if self.speech_time < MIN_SPEECH_S:
            # Too little talking for a chunk (a cough in a long silence).
            # Forget it, so two coughs a minute apart don't add up to speech.
            self.speech_time = 0.0
            return False
        self.last_pause = self._tail_s = self.silence_time
        self.speech_time = 0.0
        self.silence_time = 0.0
        return True

    def tail_samples(self) -> int:
        """Samples of measured silence to drop from the chunk just cut."""
        return max(0, int((self._tail_s - TAIL_KEEP_S) * self.sample_rate))


class ChunkWorker:
    """Transcribes and types chunks one at a time, in the order they were cut.

    One per service process (app._chunk_worker), so a new recording's chunks
    can never overtake the last one's. Each job runs holding *lock*
    (app._inject_lock), the lock that already keeps two dictations from
    typing at once.
    """

    def __init__(self, lock=None):
        self._lock = lock if lock is not None else threading.Lock()
        self._queue = queue.Queue()
        threading.Thread(target=self._run, daemon=True, name="tt-chunks").start()

    def submit(self, job) -> None:
        self._queue.put(job)

    def drain(self, timeout=None) -> bool:
        """Wait until every submitted job has finished. False on timeout."""
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._queue.all_tasks_done:
            while self._queue.unfinished_tasks:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._queue.all_tasks_done.wait(remaining)
        return True

    def _run(self):
        while True:
            job = self._queue.get()
            try:
                with self._lock:
                    job()
            except Exception:
                logger.exception("A dictation chunk failed; carrying on with the next")
            finally:
                self._queue.task_done()

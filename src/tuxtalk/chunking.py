"""Chunked dictation: type each phrase at the pause after it.

While a recording runs, PauseDetector listens for the speaker pausing. At each
pause the audio so far is handed to ChunkWorker, which transcribes and types it
while the speaker goes on talking. The result is finished phrases appearing at
natural pauses, never words appearing and changing mid-sentence (upstream's
"live text", which it decided against).

Off unless chunked_dictation is set in config.toml; see app._arm_chunker.
"""
from .silence import NoiseFloor, block_rms

# Talking needed before a pause can end a chunk: a cough or a click is shorter.
MIN_SPEECH_S = 0.3
# Silence kept at the end of a chunk, so the last word's decay is never cut.
TAIL_KEEP_S = 0.3


class PauseDetector:
    """Feed it the recording's audio blocks; it says when a chunk ends.

    Unlike silence.SilenceDetector (which ends the recording once), this fires
    at every pause and then waits for new speech before it can fire again.
    """

    def __init__(self, pause_seconds: float, sample_rate: int):
        self.pause_seconds = float(pause_seconds)
        self.sample_rate = int(sample_rate)
        self._floor = NoiseFloor()
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

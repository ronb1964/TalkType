"""
Hands-free auto-stop: notice when the speaker has finished talking.

Used only for toggle recordings (tap the toggle key, talk, and it stops on its
own). A hold recording already ends when the key is released.

This decides WHEN to stop and never removes audio from the start or middle of
a recording. That distinction matters: v0.5.16 turned off Whisper's built-in
voice-activity filter because trimming audio clipped the first words after a
pause. The only audio ever dropped is the silent tail this detector measured
(see tail_to_trim), which is safe and also keeps Whisper from inventing words
like "thank you" in trailing silence.

How it listens: each audio block's loudness (RMS) is compared with the room's
background noise, which it learns as it goes (the quietest level heard, rising
slowly if the room gets noisier). Nothing counts until the speaker has
actually talked for a moment, so a slow start is never mistaken for being
done, and a single click or bump does not count as talking.
"""
import numpy as np

# Speech must be this much louder than the background noise (about +8 dB)...
_SPEECH_OVER_NOISE = 2.5
# ...and never quieter than this, so a silent room with a near-zero noise
# floor does not turn breathing into "speech". int16 RMS; ~-40 dBFS.
_MIN_SPEECH_RMS = 300.0
# How much talking arms the detector: a cough or a click is shorter than this.
_SPEECH_TO_ARM_S = 0.3
# Keep this much of the silent tail when trimming, so the last word's natural
# decay is never cut.
_TAIL_KEEP_S = 0.3
# How fast the learned noise floor may rise per second (x1.5/s), so it follows
# a room that gets noisier without ever chasing the speaker's own voice up.
_NOISE_RISE_PER_S = 1.5


class SilenceDetector:
    """Feed it audio blocks as they arrive; it says when the speaker is done."""

    def __init__(self, silence_seconds: float, sample_rate: int):
        self.silence_seconds = float(silence_seconds)
        self.sample_rate = int(sample_rate)
        self.noise_floor = None
        self.speech_time = 0.0
        self.silence_time = 0.0
        self.fired = False

    @property
    def armed(self) -> bool:
        return self.speech_time >= _SPEECH_TO_ARM_S

    def _threshold(self) -> float:
        return max(_MIN_SPEECH_RMS, (self.noise_floor or 0.0) * _SPEECH_OVER_NOISE)

    def feed(self, block) -> bool:
        """Add one block of int16 samples. True exactly once: when the speaker
        has been silent for silence_seconds after having talked."""
        samples = np.frombuffer(block, dtype=np.int16).astype(np.float64)
        if samples.size == 0:
            return False
        duration = samples.size / self.sample_rate
        rms = float(np.sqrt(np.mean(samples ** 2)))

        if self.fired:
            # A few blocks still arrive before the recording actually stops.
            # Keep measuring them so tail_to_trim() covers the whole silent end.
            self.silence_time = self.silence_time + duration if rms < self._threshold() else 0.0
            return False

        # Learn the background noise: the quietest level heard so far, allowed
        # to rise slowly while it is quiet. Speech has short gaps between
        # syllables where only the room is heard, so even when someone starts
        # talking the instant recording begins, the floor settles on the room
        # within the first word or two.
        if self.noise_floor is None:
            # The first block may already be speech (talking the instant the
            # key goes down), so the first guess is capped at a quiet level;
            # in a noisier room it rises to the real noise within a second.
            self.noise_floor = min(rms, _MIN_SPEECH_RMS)
        elif rms < self.noise_floor:
            self.noise_floor = rms
        elif rms < self._threshold():
            self.noise_floor = min(rms, self.noise_floor * (_NOISE_RISE_PER_S ** duration))

        if rms >= self._threshold():
            self.speech_time += duration
            self.silence_time = 0.0
            return False

        if not self.armed:
            return False
        self.silence_time += duration
        if self.silence_time >= self.silence_seconds:
            self.fired = True
            return True
        return False

    def tail_to_trim(self) -> int:
        """Samples of measured silence to drop from the end once it fired."""
        if not self.fired:
            return 0
        return max(0, int((self.silence_time - _TAIL_KEEP_S) * self.sample_rate))

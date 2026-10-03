"""Parakeet on the graphics chip: the helper process and its protocol.

The real helper (parakeet_gpu_worker.py) needs a graphics chip and the engine,
and was checked by hand on an RTX 4070 Super. These tests run a stand-in
helper that speaks the same protocol, so the start-up, transcription, crash
and fallback paths are all exercised through a real process and real pipes.
"""
import io
import sys
import textwrap

import numpy as np
import pytest

from talktype import parakeet_gpu
from talktype import parakeet_gpu_worker as worker

# A stand-in helper. Behaviour is picked by its first argument:
#   ok      answers "<n> samples" for each request
#   refuse  reports an error instead of becoming ready
#   die     becomes ready, then exits on the first request
#   once    answers the first request, then exits
FAKE_WORKER = textwrap.dedent("""
    import json, struct, sys
    mode = sys.argv[1]
    out, inp = sys.stdout.buffer, sys.stdin.buffer
    def reply(obj):
        out.write((json.dumps(obj) + "\\n").encode()); out.flush()
    if mode == "refuse":
        reply({"error": "no graphics chip"}); sys.exit(1)
    reply({"ready": True})
    answered = 0
    while True:
        head = inp.read(4)
        if len(head) < 4:
            break
        n = struct.unpack("<I", head)[0]
        inp.read(n * 4)
        if mode == "die" or (mode == "once" and answered):
            sys.exit(3)
        reply({"text": f" {n} samples "})
        answered += 1
""")


@pytest.fixture
def fake(tmp_path):
    script = tmp_path / "fake_worker.py"
    script.write_text(FAKE_WORKER)
    return lambda mode: [sys.executable, str(script), mode]


def _audio(seconds=1.0):
    return np.zeros(int(16000 * seconds), dtype=np.float32)


def test_transcribes_through_the_helper(fake):
    model = parakeet_gpu.ParakeetGpuModel(0, command=fake("ok"))
    try:
        assert model.recognize(_audio(2)) == "32000 samples"
        assert model.recognize(_audio(3)) == "48000 samples"
    finally:
        model.close()


def test_very_short_audio_is_padded_to_a_second(fake):
    """A tap of the key can record almost nothing; the engine gets at least
    a second, padded with silence, rather than a near-empty buffer."""
    model = parakeet_gpu.ParakeetGpuModel(0, command=fake("ok"))
    try:
        assert model.recognize(_audio(0.1)) == "16000 samples"
    finally:
        model.close()


def test_a_helper_that_cannot_start_says_why(fake):
    with pytest.raises(RuntimeError, match="no graphics chip"):
        parakeet_gpu.ParakeetGpuModel(0, command=fake("refuse"))


def test_a_crashed_helper_is_started_again(fake):
    model = parakeet_gpu.ParakeetGpuModel(0, command=fake("once"))
    try:
        assert model.recognize(_audio()) == "16000 samples"
        # The helper exits on its second request; a fresh one answers it.
        assert model.recognize(_audio(2)) == "32000 samples"
    finally:
        model.close()


def test_falls_back_to_the_processor_when_the_helper_keeps_failing(fake, monkeypatch):
    class Cpu:
        def recognize(self, audio):
            return "from the processor"

    monkeypatch.setattr(parakeet_gpu, "load_parakeet_model", lambda: Cpu())
    model = parakeet_gpu.ParakeetGpuModel(0, command=fake("die"))
    try:
        assert model.recognize(_audio()) == "from the processor"
        assert model.recognize(_audio()) == "from the processor"   # stays there
    finally:
        model.close()


def test_no_processor_model_to_fall_back_to_is_an_error(fake, monkeypatch):
    def missing():
        raise FileNotFoundError("Parakeet model has not been downloaded")

    monkeypatch.setattr(parakeet_gpu, "load_parakeet_model", missing)
    model = parakeet_gpu.ParakeetGpuModel(0, command=fake("die"))
    try:
        with pytest.raises(RuntimeError, match="graphics"):
            model.recognize(_audio())
    finally:
        model.close()


# --- the helper's side of the protocol -------------------------------------------

def test_worker_reads_one_request_at_a_time_and_stops_at_the_end():
    samples = np.arange(5, dtype=np.float32)
    stream = io.BytesIO(worker.encode_request(samples) + worker.encode_request(samples[:2]))
    assert np.frombuffer(worker.read_request(stream), np.float32).tolist() == [0, 1, 2, 3, 4]
    assert np.frombuffer(worker.read_request(stream), np.float32).tolist() == [0, 1]
    assert worker.read_request(stream) is None


def test_worker_replies_are_single_json_lines():
    out = io.BytesIO()
    worker.write_reply(out, {"text": "two\nlines"})
    assert out.getvalue().count(b"\n") == 1


def test_segments_are_joined_into_one_line_of_text():
    assert worker.join_segments([" And so,", " my fellow", "Americans. "]) == \
        "And so, my fellow Americans."
    assert worker.join_segments([]) == ""


def test_a_restart_on_a_short_lived_thread_outlives_that_thread(fake):
    """The helper dies with the thread that started it. A restart from a
    dictation thread that then ends must leave a helper that keeps working."""
    import threading
    model = parakeet_gpu.ParakeetGpuModel(0, command=fake("once"))
    try:
        model.recognize(_audio())
        results = []
        t = threading.Thread(target=lambda: results.append(model.recognize(_audio(2))))
        t.start()
        t.join()                                  # restarted the helper, then ended
        assert results == ["32000 samples"]
        assert model._proc.poll() is None         # still running
        assert model.recognize(_audio(3)) == "48000 samples"
    finally:
        model.close()

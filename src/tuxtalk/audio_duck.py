"""Turn other sounds down while dictating (config duck_audio).

Pausing (media_pause.py) only reaches players that answer media keys. A
Discord call, a game or a video in an app without MPRIS keeps playing into
the microphone. So while a recording runs, every other app's sound is turned
down to a quarter, and put back when it ends. A stream whose volume the user
changed in the meantime is left as they set it.

It talks to PipeWire or PulseAudio through pactl (pulseaudio-utils, present
on every desktop that uses either). TuxTalk's own streams, its beeps, are
never touched.

If the service stops mid-dictation, the volumes it lowered are written to a
small file in the runtime folder, and the next start puts them back
(restore_left_over), so nothing stays quiet for good.

Like media_pause, all the work runs on one background thread: duck() is
called while every keyboard is grabbed and must never wait on pactl.
"""
import json
import os
import queue
import subprocess
import threading

from .logger import setup_logger

logger = setup_logger(__name__)

DUCK_TO = 0.25          # other apps play at a quarter of their volume
PACTL_TIMEOUT_S = 2.0
STATE_FILE = "tuxtalk-ducked-audio.json"


def _state_path():
    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return os.path.join(runtime, STATE_FILE)


def _pactl(*args, run=subprocess.run):
    """pactl's output, or None if it isn't there or fails."""
    try:
        result = run(["pactl", *args], capture_output=True, text=True, timeout=PACTL_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.debug(f"Audio duck: pactl {args[0] if args else ''} failed: {e}")
        return None
    if result.returncode != 0:
        logger.debug(f"Audio duck: pactl {' '.join(args)}: {result.stderr.strip()}")
        return None
    return result.stdout


def list_streams(run=subprocess.run):
    """[(index, pid, [channel volumes, raw], muted)] of the apps playing now."""
    out = _pactl("-f", "json", "list", "sink-inputs", run=run)
    if not out:
        return []
    try:
        streams = json.loads(out)
    except ValueError:
        return []
    found = []
    for s in streams:
        try:
            props = s.get("properties", {})
            pid = int(props.get("application.process.id") or 0)
            volumes = [int(ch["value"]) for ch in s.get("volume", {}).values()]
            found.append((int(s["index"]), pid, volumes, bool(s.get("mute"))))
        except (KeyError, TypeError, ValueError):
            continue
    return found


def _set_volume(index, volumes, run=subprocess.run):
    return _pactl("set-sink-input-volume", str(index), *[str(v) for v in volumes], run=run) is not None


class AudioDucker:
    """duck() lowers every other app; restore() puts back what it lowered."""

    def __init__(self, run=subprocess.run, own_pid=None, state_path=None):
        self._run = run
        self._own_pid = os.getpid() if own_pid is None else own_pid
        self._state_path = state_path or _state_path()
        self._ducked = {}          # index -> (original volumes, ducked volumes)
        self._jobs = queue.Queue()
        self._worker = None

    # -- called from the dictation service; never block -------------------

    def duck(self):
        self._submit(self._duck_now)

    def restore(self):
        self._submit(self._restore_now)

    def restore_now(self):
        """Restore on the calling thread. For exit, when the worker may not get a turn."""
        self._restore_now()

    def wait_idle(self, timeout):
        """Wait for queued jobs to finish (tests). True if they did."""
        done = threading.Event()
        self._submit(done.set)
        return done.wait(timeout)

    # -- the worker -------------------------------------------------------

    def _submit(self, job):
        if self._worker is None:
            self._worker = threading.Thread(target=self._run_jobs, name="audio-duck", daemon=True)
            self._worker.start()
        self._jobs.put(job)

    def _run_jobs(self):
        while True:
            job = self._jobs.get()
            try:
                job()
            except Exception as e:
                logger.debug(f"Audio duck: {e}")

    def _duck_now(self):
        for index, pid, volumes, muted in list_streams(self._run):
            if pid == self._own_pid or muted or index in self._ducked or not volumes:
                continue
            lowered = [max(0, int(v * DUCK_TO)) for v in volumes]
            if _set_volume(index, lowered, self._run):
                self._ducked[index] = (volumes, lowered)
        if self._ducked:
            logger.info(f"Turned {len(self._ducked)} other sound(s) down while dictating")
            self._save()

    def _restore_now(self):
        ducked, self._ducked = self._ducked, {}
        if not ducked:
            return
        now = {index: volumes for index, _pid, volumes, _m in list_streams(self._run)}
        put_back = 0
        for index, (original, lowered) in ducked.items():
            # Gone, or the user set its volume themselves meanwhile: leave it.
            if now.get(index) != lowered:
                continue
            if _set_volume(index, original, self._run):
                put_back += 1
        logger.info(f"Put {put_back} sound(s) back to their volume")
        self._clear()

    def _save(self):
        try:
            data = {str(i): {"original": o, "lowered": low} for i, (o, low) in self._ducked.items()}
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError as e:
            logger.debug(f"Audio duck: could not save {self._state_path}: {e}")

    def _clear(self):
        try:
            os.remove(self._state_path)
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.debug(f"Audio duck: could not remove {self._state_path}: {e}")


def restore_left_over(run=subprocess.run, state_path=None):
    """Put back volumes a service that stopped mid-dictation left lowered."""
    path = state_path or _state_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return 0
    except (OSError, ValueError):
        data = {}
    ducker = AudioDucker(run=run, state_path=path)
    for index, entry in data.items():
        try:
            ducker._ducked[int(index)] = ([int(v) for v in entry["original"]],
                                          [int(v) for v in entry["lowered"]])
        except (KeyError, TypeError, ValueError):
            continue
    if ducker._ducked:
        logger.info("Putting back sounds a stopped dictation left turned down")
    count = len(ducker._ducked)
    ducker._restore_now()
    ducker._clear()
    return count

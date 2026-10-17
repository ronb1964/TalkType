"""Turn other sounds down while dictating (config duck_audio).

Pausing (media_pause.py) only reaches players that answer media keys. A
Discord call, a game or a video in an app without MPRIS keeps playing into
the microphone. So while a recording runs, every other app's sound is turned
down to a quarter, and put back when it ends. A stream whose volume the user
changed in the meantime is left as they set it.

It talks to PipeWire or PulseAudio through pactl (pulseaudio-utils, present
on every desktop that uses either). TuxTalk's own streams, its beeps, are
never touched: on PipeWire a stream doesn't carry its process id, its client
does, so streams are matched to their client's pid. Short system sounds
(media.role "event") are left alone too.

The desktop remembers each app's volume. A sound that ends while it's turned
down (a beep, a notification) would come back that quiet next time, and a
second dictation would lower it again. So such an app is remembered as owed
its volume (by application.name, the desktop's own key) until TuxTalk next
sees it at the lowered level and puts it back; it's never lowered from there.
On 2026-10-17 the beeps did exactly that and went silent in three presses.

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
# After a dictation, look again this long after (seconds) for an app owed
# its volume: a browser closes its sound while its video is paused and opens
# a new one on resume, a moment after TuxTalk restored, at the lowered level.
FOLLOW_UP_S = (0.5, 1.0, 2.0, 4.0, 8.0)
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


def _client_pids(run=subprocess.run):
    """{client index: pid} from pactl's clients, where PipeWire puts the pid."""
    out = _pactl("-f", "json", "list", "clients", run=run)
    try:
        clients = json.loads(out) if out else []
    except ValueError:
        return {}
    pids = {}
    for c in clients:
        try:
            pid = int(c.get("properties", {}).get("application.process.id") or 0)
            if pid:
                pids[int(c["index"])] = pid
        except (KeyError, TypeError, ValueError):
            continue
    return pids


def list_streams(run=subprocess.run):
    """The apps playing now: dicts of index, pid (0 if unknown), app (its
    application.name), role, volumes ([channel volumes, raw]) and muted."""
    out = _pactl("-f", "json", "list", "sink-inputs", run=run)
    if not out:
        return []
    try:
        streams = json.loads(out)
    except ValueError:
        return []
    clients = None
    found = []
    for s in streams:
        try:
            props = s.get("properties", {})
            pid = int(props.get("application.process.id") or 0)
            if not pid and s.get("client") not in (None, ""):
                if clients is None:
                    clients = _client_pids(run)
                pid = clients.get(int(s["client"]), 0)
            found.append({"index": int(s["index"]), "pid": pid,
                          "app": props.get("application.name") or "",
                          "role": props.get("media.role") or "",
                          "volumes": [int(ch["value"]) for ch in s.get("volume", {}).values()],
                          "muted": bool(s.get("mute")),
                          "corked": bool(s.get("corked"))})
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
        self._ducked = {}          # index -> (original volumes, ducked volumes, app)
        # app -> {"original":, "lowered":}: its stream ended while turned
        # down, so the desktop remembers it lowered (see the top).
        self._owed = self._load_owed()
        self._jobs = queue.Queue()
        self._worker = None
        self._round = 0            # each duck starts a new one; old follow-ups stop

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
        self._round += 1
        streams = list_streams(self._run)
        self._settle_owed(streams)
        for st in streams:
            index, volumes = st["index"], st["volumes"]
            # Paused (corked) already: silent, and likely to close and come
            # back as a new stream, so there's nothing to gain lowering it.
            if (st["pid"] == self._own_pid or st["muted"] or st["role"] == "event"
                    or st["corked"] or index in self._ducked or not volumes):
                continue
            lowered = [max(0, int(v * DUCK_TO)) for v in volumes]
            if _set_volume(index, lowered, self._run):
                self._ducked[index] = (volumes, lowered, st["app"])
        if self._ducked:
            logger.info(f"Turned {len(self._ducked)} other sound(s) down while dictating")
        self._save()

    def _restore_now(self):
        ducked, self._ducked = self._ducked, {}
        if not ducked and not self._owed:
            return
        streams = list_streams(self._run)
        now = {st["index"]: st["volumes"] for st in streams}
        put_back = 0
        for index, (original, lowered, app) in ducked.items():
            if index not in now:
                # Ended while turned down: the desktop keeps it that quiet for
                # the app's next sound, until it's seen and put back.
                if app:
                    self._owed[app] = {"original": original, "lowered": lowered}
                continue
            if now[index] != lowered:
                continue        # the user set its volume themselves meanwhile
            if _set_volume(index, original, self._run):
                put_back += 1
        put_back += self._settle_owed(streams)
        if ducked:
            logger.info(f"Put {put_back} sound(s) back to their volume")
        self._save()
        if self._owed:
            self._follow_up(self._round, 0)

    def _follow_up(self, round_, step):
        """Look again for apps owed their volume, at FOLLOW_UP_S, until none
        is owed or a new dictation starts (which settles them itself)."""
        if step >= len(FOLLOW_UP_S):
            return
        wait = FOLLOW_UP_S[step] - (FOLLOW_UP_S[step - 1] if step else 0)

        def due():
            self._submit(lambda: self._settle_later(round_, step))
        timer = threading.Timer(wait, due)
        timer.daemon = True
        timer.start()

    def _settle_later(self, round_, step):
        if round_ != self._round or self._ducked or not self._owed:
            return
        self._settle_owed(list_streams(self._run))
        self._save()
        if self._owed:
            self._follow_up(round_, step + 1)

    def _settle_owed(self, streams):
        """Put back an app owed its volume, playing now at the lowered level;
        its streams are then counted at their real volume. How many."""
        fixed = 0
        for st in streams:
            owed = self._owed.get(st["app"])
            if owed is None or st["index"] in self._ducked:
                continue
            if st["volumes"] == owed["lowered"] and _set_volume(st["index"], owed["original"], self._run):
                st["volumes"] = list(owed["original"])
                fixed += 1
            # At the lowered level or not (the user set another), it's settled.
            del self._owed[st["app"]]
        if fixed:
            logger.info(f"Put {fixed} app(s) back to the volume a dictation turned down")
        return fixed

    def _save(self):
        if not self._ducked and not self._owed:
            self._clear()
            return
        try:
            data = {str(i): {"original": o, "lowered": low, "app": app}
                    for i, (o, low, app) in self._ducked.items()}
            data["owed"] = self._owed
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError as e:
            logger.debug(f"Audio duck: could not save {self._state_path}: {e}")

    def _load_owed(self):
        try:
            with open(self._state_path, encoding="utf-8") as f:
                owed = json.load(f).get("owed", {})
            return {str(app): {"original": [int(v) for v in e["original"]],
                               "lowered": [int(v) for v in e["lowered"]]}
                    for app, e in owed.items()}
        except (OSError, ValueError, AttributeError, KeyError, TypeError):
            return {}

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
        if index == "owed":
            continue
        try:
            ducker._ducked[int(index)] = ([int(v) for v in entry["original"]],
                                          [int(v) for v in entry["lowered"]],
                                          str(entry.get("app", "")))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    if ducker._ducked:
        logger.info("Putting back sounds a stopped dictation left turned down")
    count = len(ducker._ducked)
    ducker._restore_now()       # what's still owed stays in the file for later
    return count

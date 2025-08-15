import os, sys, time, shutil, subprocess, tempfile, wave, atexit, argparse
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from evdev import InputDevice, ecodes, list_devices

from .normalize import normalize_text
from .config import load_config, Settings

# Optional desktop notifications via libnotify (gi)
_notify_ready = False
try:
    import gi
    gi.require_version("Notify", "0.7")
    from gi.repository import Notify
    Notify.init("Ron Dictation")
    _notify_ready = True
except Exception:
    _notify_ready = False

def _notify(title: str, body: str):
    if not _notify_ready:
        return
    try:
        n = Notify.Notification.new(title, body)
        n.show()
    except Exception:
        pass

# --- Single instance lock (user runtime dir) ---
def _runtime_dir():
    return os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

_PIDFILE = os.path.join(_runtime_dir(), "ron-dictation.pid")

def _pid_running(pid: int) -> bool:
    if pid <= 0: return False
    proc = f"/proc/{pid}"
    if not os.path.exists(proc): return False
    try:
        with open(os.path.join(proc, "cmdline"), "rb") as f:
            cmd = f.read().decode(errors="ignore")
        return ("ron_dictation.app" in cmd) or ("dictate" in cmd)
    except Exception:
        return True  # if in doubt, assume running

def _acquire_single_instance():
    try:
        if os.path.exists(_PIDFILE):
            try:
                with open(_PIDFILE, "r") as f:
                    old = int(f.read().strip() or "0")
            except Exception:
                old = 0
            if _pid_running(old):
                print("Another ron-dictation instance is already running. Exiting.")
                sys.exit(0)
        with open(_PIDFILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        print(f"Warning: could not write pidfile: {e}")
    def _cleanup():
        try:
            with open(_PIDFILE, "r") as f:
                cur = int(f.read().strip() or "0")
            if cur == os.getpid():
                os.remove(_PIDFILE)
        except Exception:
            pass
    atexit.register(_cleanup)

# --- Runtime state ---
SAMPLE_RATE = 16000
CHANNELS = 1
MIN_HOLD_MS = 200
START_BEEP = (1200, 0.12)
CANCEL_BEEP = (500, 0.12)
READY_BEEP  = (1000, 0.09)

is_recording = False
was_cancelled = False
frames = []
stream = None
press_t0 = None
# Deprecated: we now inject space immediately after finishing an utterance when needed
prepend_space_next_time = False

def _beep(enabled: bool, freq=1000, duration=0.15):
    if not enabled:
        return
    samplerate = 44100
    t = np.linspace(0, duration, int(samplerate * duration), False)
    tone = (np.sin(freq * t * 2 * np.pi) * 0.2).astype(np.float32)
    try:
        sd.play(tone, samplerate); sd.wait()
    except Exception:
        pass

def _sd_callback(indata, frames_count, time_info, status):
    if is_recording:
        frames.append(indata.tobytes())

def _keycode_from_name(name: str) -> int:
    n = (name or "F8").strip().upper()
    fkeys = {f"F{i}": getattr(ecodes, f"KEY_F{i}") for i in range(1,13)}
    if n in fkeys: return fkeys[n]
    if len(n) == 1 and "A" <= n <= "Z":
        return getattr(ecodes, f"KEY_{n}")
    return ecodes.KEY_F8

def _pick_input_device(mic_substring: str | None):
    """Return device index or None for default."""
    try:
        q = sd.query_devices()
    except Exception:
        return None
    if not mic_substring:
        return None
    m = mic_substring.lower()
    candidates = [ (i,d) for i,d in enumerate(q) if d.get("max_input_channels",0) > 0 and m in d.get("name","").lower() ]
    if candidates:
        return candidates[0][0]
    return None

def start_recording(beeps_on: bool, notify_on: bool, input_device_idx):
    global is_recording, was_cancelled, frames, stream, press_t0
    frames = []
    was_cancelled = False
    is_recording = True
    press_t0 = time.time()
    sd.default.channels = CHANNELS
    sd.default.samplerate = SAMPLE_RATE
    stream = sd.InputStream(callback=_sd_callback, dtype='int16', device=input_device_idx)
    stream.start()
    print("🎙️  Recording…")
    _beep(beeps_on, *START_BEEP)
    if notify_on: _notify("Ron Dictation", "Recording… (speak now)")

def _stop_stream_safely():
    global stream
    if stream:
        try:
            stream.stop(); stream.close()
        except Exception:
            pass
        stream = None

def cancel_recording(beeps_on: bool, notify_on: bool, reason="Cancelled"):
    global is_recording, was_cancelled
    is_recording = False
    was_cancelled = True
    _stop_stream_safely()
    _beep(beeps_on, *CANCEL_BEEP)
    print(f"⏸️  {reason}")
    if notify_on: _notify("Ron Dictation", reason)

def _type_text(text: str):
    if shutil.which("ydotool"):
        try:
            env = os.environ.copy()
            runtime = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            env.setdefault("YDOTOOL_SOCKET", os.path.join(runtime, ".ydotool_socket"))
            proc = subprocess.Popen(
                ["ydotool", "type", "-d", "5", "-H", "5", "-f", "-"],
                stdin=subprocess.PIPE,
                env=env
            )
            proc.communicate(input=text.encode("utf-8"), timeout=20)
            return
        except Exception as e:
            print(f"ydotool failed: {e}")
    if shutil.which("wtype"):
        subprocess.run(["wtype", "--", text], check=False); return
    if shutil.which("wl-copy"):
        try:
            import pyperclip
            pyperclip.copy(text); print("📋 Copied to clipboard. Ctrl+V to paste.")
            return
        except Exception:
            pass
    print("⚠️  Could not type text (no ydotool/wtype).")

def _paste_text(text: str):
    """Wayland paste injection: put text on clipboard, then Ctrl+V."""
    try:
        if shutil.which("wl-copy") and shutil.which("ydotool"):
            # Copy text
            import subprocess as _sp
            _sp.run(["wl-copy"], input=text.encode("utf-8"), check=False)
            # Give the compositor a moment to publish clipboard contents
            time.sleep(0.06)
            # Send Ctrl+V: KEY_LEFTCTRL (29), KEY_V (47)
            env = os.environ.copy()
            runtime = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            env.setdefault("YDOTOOL_SOCKET", os.path.join(runtime, ".ydotool_socket"))
            _sp.run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"], check=False, env=env)
            # Some apps prefer Shift+Insert; try it as well just in case
            _sp.run(["ydotool", "key", "42:1", "110:1", "110:0", "42:0"], check=False, env=env)
            time.sleep(0.02)
            return True
    except Exception:
        pass
    return False

def _press_space():
    # Inject a literal Space keypress via ydotool when possible; fallback to typing a space
    if shutil.which("ydotool"):
        try:
            env = os.environ.copy()
            runtime = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            env.setdefault("YDOTOOL_SOCKET", os.path.join(runtime, ".ydotool_socket"))
            subprocess.run(["ydotool", "key", "57:1", "57:0"], check=False, env=env)
            return
        except Exception:
            pass
    if shutil.which("wtype"):
        subprocess.run(["wtype", "--", " "], check=False); return

def stop_recording(
    beeps_on: bool,
    smart_quotes: bool,
    notify_on: bool,
    language: str | None = None,
    auto_space: bool = True,
    auto_period: bool = False,
    paste_injection: bool = False,
):
    global is_recording
    held_ms = int((time.time() - (press_t0 or time.time())) * 1000)
    if held_ms < MIN_HOLD_MS:
        cancel_recording(beeps_on, notify_on, f"Cancelled (held {held_ms} ms)"); return
    is_recording = False
    _stop_stream_safely()
    if was_cancelled: return

    print("🛑 Recording stopped. Transcribing…")
    # Convert captured bytes -> float32 mono PCM in [-1, 1]
    try:
        pcm_int16 = np.frombuffer(b''.join(frames), dtype=np.int16)
        if pcm_int16.size == 0:
            print("ℹ️  (No audio captured)")
            return
        audio_f32 = (pcm_int16.astype(np.float32) / 32768.0)

        segments, _ = model.transcribe(
            audio_f32,
            vad_filter=True,
            beam_size=1,
            condition_on_previous_text=False,
            temperature=0.0,
            without_timestamps=True,
            language=(language or None),
        )
        raw = " ".join(seg.text for seg in segments).strip()
        print(f"📝 Raw: {raw!r}")
        text = normalize_text(raw if smart_quotes else raw.replace("“","\"").replace("”","\""))

        # Simple spacing: always add period+space or just space when auto features are on
        if auto_period and text and not text.rstrip().endswith((".","?","!","…")):
            text = text.rstrip() + "."
        if auto_space and text and not text.endswith((" ", "\n", "\t")):
            text = text + " "
        print(f"📜 Text: {text!r}")

        _beep(beeps_on, *READY_BEEP)
        if notify_on: _notify("Ron Dictation", f"Transcribed: {text[:80]}{'…' if len(text)>80 else ''}")
        if text:
            # Small settling delay so focused app is ready to receive text
            time.sleep(0.12)
            # Choose injection mode: paste entire utterance vs keystroke typing
            use_paste = paste_injection or os.environ.get("DICTATE_INJECTION_MODE","type").lower()=="paste"
            if use_paste and _paste_text(text):
                print(f"✂️  Inject (paste) len={len(text)}")
                pass
            else:
                print(f"⌨️  Inject (type) len={len(text)}")
                _type_text(text)
            # We appended trailing spacing already when needed; do not request a leading space next time.
            prepend_space_next_time = False
            # Update spacing flag for next utterance
            import re as _re
            # If the last visible character is not whitespace/newline/tab, we should lead with space next time
            last_utterance_should_lead_with_space = bool(_re.search(r"[^\s]$", text))
        else: print("ℹ️  (No speech recognized)")
    except Exception as e:
        print(f"Transcription error: {e}")

def _loop_evdev(cfg: Settings, input_device_idx):
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    print(f"Session: {session} | Wayland={session=='wayland'}")
    mode = cfg.mode.lower().strip()
    print(f"Mode: {mode} | Hold key: {cfg.hotkey}" + (f" | Toggle key: {cfg.toggle_hotkey}" if mode=='toggle' else ""))
    devices = [InputDevice(p) for p in list_devices()]
    for dev in devices:
        try: dev.set_nonblocking(True)
        except Exception: pass

    hold_key = _keycode_from_name(cfg.hotkey)
    toggle_key = _keycode_from_name(cfg.toggle_hotkey) if mode == "toggle" else None

    global is_recording
    while True:
        for dev in devices:
            try:
                for event in dev.read():
                    if event.type == ecodes.EV_KEY:
                        if mode == "hold":
                            if event.code == hold_key:
                                if event.value == 1 and not is_recording:
                                    start_recording(cfg.beeps, cfg.notify, input_device_idx)
                                elif event.value == 0 and is_recording:
                                    stop_recording(cfg.beeps, cfg.smart_quotes, cfg.notify, cfg.language, cfg.auto_space, cfg.auto_period, cfg.paste_injection)
                        else:  # toggle mode: press to start, press again to stop
                            if event.code == toggle_key and event.value == 1:
                                if not is_recording:
                                    start_recording(cfg.beeps, cfg.notify, input_device_idx)
                                else:
                                     stop_recording(cfg.beeps, cfg.smart_quotes, cfg.notify, cfg.language, cfg.auto_space, cfg.auto_period, cfg.paste_injection)
                        # ESC cancels in any mode
                        if event.code == ecodes.KEY_ESC and is_recording and event.value == 1:
                            cancel_recording(cfg.beeps, cfg.notify, "Cancelled by ESC")
            except BlockingIOError:
                pass
            except Exception:
                pass
        time.sleep(0.005)

def build_model(settings: Settings):
    compute_type = "float16" if settings.device.lower() == "cuda" else "int8"
    return WhisperModel(
        settings.model,
        device=settings.device,
        compute_type=compute_type,
        cpu_threads=os.cpu_count() or 4
    )

def parse_args():
    ap = argparse.ArgumentParser(prog="dictate", description="Press-and-hold / toggle dictation for Wayland")
    ap.add_argument("--model", help="Whisper model (tiny/base/small/medium/large-v3)", default=None)
    ap.add_argument("--device", help="Device (cpu/cuda)", default=None)
    ap.add_argument("--hotkey", help="Hold-to-talk hotkey (F1..F12 or a-z)", default=None)
    ap.add_argument("--mode", choices=["hold","toggle"], help="Activation mode", default=None)
    ap.add_argument("--toggle-hotkey", help="Toggle key (F1..F12 or a-z) when mode=toggle", default=None)
    ap.add_argument("--mic", help="Substring of input device name to use", default=None)
    ap.add_argument("--beeps", choices=["on","off"], help="Enable beeps", default=None)
    ap.add_argument("--smart-quotes", choices=["on","off"], help="Use “smart quotes”", default=None)
    ap.add_argument("--notify", choices=["on","off"], help="Desktop notifications", default=None)
    ap.add_argument("--language", help="Force language code (e.g., en). Empty = auto-detect", default=None)
    return ap.parse_args()

def main():
    _acquire_single_instance()

    cfg = load_config()
    args = parse_args()

    if args.model: cfg.model = args.model
    if args.device: cfg.device = args.device
    if args.hotkey: cfg.hotkey = args.hotkey
    if args.mode: cfg.mode = args.mode
    if args.toggle_hotkey: cfg.toggle_hotkey = args.toggle_hotkey
    if args.mic is not None: cfg.mic = args.mic
    if args.beeps: cfg.beeps = (args.beeps == "on")
    if args.smart_quotes: cfg.smart_quotes = (args.smart_quotes == "on")
    if args.notify: cfg.notify = (args.notify == "on")
    if args.language is not None: cfg.language = args.language

    # Input device selection
    input_device_idx = _pick_input_device(cfg.mic)

    global model
    model = build_model(cfg)
    print(f"Config: model={cfg.model} device={cfg.device} lang={cfg.language or 'auto'} auto_space={cfg.auto_space} auto_period={cfg.auto_period}")
    _loop_evdev(cfg, input_device_idx)

if __name__ == "__main__":
    main()

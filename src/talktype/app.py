# Import torch_init FIRST to configure CUDA library paths before any torch imports
from .torch_init import init_cuda_for_pytorch
init_cuda_for_pytorch()

import os, sys, time, shutil, subprocess, tempfile, wave, atexit, argparse, fcntl
from dataclasses import dataclass
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from evdev import InputDevice, ecodes, list_devices

from .normalize import normalize_text
from .config import load_config, Settings
from .logger import setup_logger

logger = setup_logger(__name__)

# Optional desktop notifications via libnotify (gi)
_notify_ready = False
try:
    import gi
    gi.require_version("Notify", "0.7")
    from gi.repository import Notify
    Notify.init("TalkType")
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

def show_hotkey_test_dialog(mode, hold_key, toggle_key):
    """Show modal dialog requiring user to test hotkeys before continuing."""
    try:
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, GLib

        dialog = Gtk.Dialog(title="Verify Your Hotkeys")
        dialog.set_default_size(520, 320)
        dialog.set_resizable(False)
        dialog.set_modal(True)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        dialog.set_keep_above(True)

        content = dialog.get_content_area()
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        content.set_margin_start(25)
        content.set_margin_end(25)
        content.set_spacing(15)

        # Header
        header = Gtk.Label()
        header.set_markup('<span size="large"><b>🎹 Verify Your Hotkeys</b></span>')
        content.pack_start(header, False, False, 0)

        # Instructions - always test both keys
        instructions = Gtk.Label()
        instructions.set_markup(
            '<b>Before you can start dictating, please test both hotkeys:</b>\n\n'
            f'1. Press <b>{hold_key}</b> (push-to-talk mode)\n'
            f'2. Press <b>{toggle_key}</b> (toggle mode)\n\n'
            'This ensures your hotkeys work and don\'t conflict with other apps.'
        )
        instructions.set_line_wrap(True)
        instructions.set_xalign(0)
        content.pack_start(instructions, False, False, 0)

        # Status labels
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        status_box.set_margin_top(10)

        hold_status = Gtk.Label()
        hold_status.set_markup(f'<b>{hold_key}</b>: <span color="#999999">⏳ Waiting...</span>')
        hold_status.set_xalign(0)
        status_box.pack_start(hold_status, False, False, 0)

        toggle_status = Gtk.Label()
        toggle_status.set_markup(f'<b>{toggle_key}</b>: <span color="#999999">⏳ Waiting...</span>')
        toggle_status.set_xalign(0)
        status_box.pack_start(toggle_status, False, False, 0)

        content.pack_start(status_box, False, False, 0)

        # Track tested keys
        tested = {"hold": False, "toggle": False}

        # Buttons
        button_box = dialog.get_action_area()
        button_box.set_layout(Gtk.ButtonBoxStyle.EDGE)

        change_keys_btn = Gtk.Button(label="Change Keys...")
        change_keys_btn.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.APPLY))
        change_keys_btn.set_tooltip_text("Open Preferences to change hotkeys")
        dialog.add_action_widget(change_keys_btn, Gtk.ResponseType.APPLY)

        skip_btn = Gtk.Button(label="Skip")
        skip_btn.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.CANCEL))
        skip_btn.set_tooltip_text("Skip verification (not recommended)")
        dialog.add_action_widget(skip_btn, Gtk.ResponseType.CANCEL)

        continue_btn = Gtk.Button(label="Continue")
        continue_btn.set_sensitive(False)  # Disabled until both keys tested
        continue_btn.get_style_context().add_class("suggested-action")
        continue_btn.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))
        dialog.add_action_widget(continue_btn, Gtk.ResponseType.OK)

        # Key press handler
        def on_key_press(widget, event):
            from gi.repository import Gdk
            keyname = Gdk.keyval_name(event.keyval)

            if keyname == hold_key and not tested["hold"]:
                tested["hold"] = True
                hold_status.set_markup(f'<b>{hold_key}</b>: <span color="#4CAF50">✓ Working!</span>')

                # Enable continue button when both keys tested
                if tested["hold"] and tested["toggle"]:
                    continue_btn.set_sensitive(True)
                    continue_btn.set_label("✓ Continue")

            elif keyname == toggle_key and not tested["toggle"]:
                tested["toggle"] = True
                toggle_status.set_markup(f'<b>{toggle_key}</b>: <span color="#4CAF50">✓ Working!</span>')

                # Enable continue button when both keys tested
                if tested["hold"] and tested["toggle"]:
                    continue_btn.set_sensitive(True)
                    continue_btn.set_label("✓ Continue")

            return True

        dialog.connect("key-press-event", on_key_press)

        # Dialog response handling
        result = {"action": None, "verified": False}

        def on_response(dialog, response_id):
            if response_id == Gtk.ResponseType.OK:
                result["action"] = "verified"
                result["verified"] = tested["hold"] and tested["toggle"]
            elif response_id == Gtk.ResponseType.APPLY:
                result["action"] = "change_keys"
            else:
                result["action"] = "skipped"
            dialog.destroy()
            Gtk.main_quit()

        dialog.connect("response", on_response)
        dialog.show_all()

        # Run a GTK main loop for this dialog
        Gtk.main()

        # Return results
        return (result["action"], result["verified"])

    except Exception as e:
        logger.error(f"Failed to show hotkey test dialog: {e}")
        return ("error", True)  # Fallback: allow continuation if dialog fails

# --- Single instance lock (user runtime dir) ---
def _runtime_dir():
    return os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

_PIDFILE = os.path.join(_runtime_dir(), "talktype.pid")

def _pid_running(pid: int) -> bool:
    if pid <= 0: return False
    proc = f"/proc/{pid}"
    if not os.path.exists(proc): return False
    try:
        with open(os.path.join(proc, "cmdline"), "rb") as f:
            cmd = f.read().decode(errors="ignore")
        return ("talktype.app" in cmd) or ("dictate" in cmd)
    except Exception:
        return True  # if in doubt, assume running

def _acquire_single_instance():
    """
    Acquire singleton lock using fcntl to prevent race conditions.
    Uses file locking which is atomic and prevents multiple instances.
    The lock is held for the lifetime of the process and auto-released on exit.
    """
    lockfile_path = os.path.join(_runtime_dir(), "talktype.lock")
    try:
        # Open lock file (create if doesn't exist)
        lockfile = open(lockfile_path, "w")

        # Try to acquire exclusive lock (non-blocking)
        # LOCK_EX = exclusive lock, LOCK_NB = non-blocking
        fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        # If we got here, we acquired the lock successfully
        # Write our PID for informational purposes
        lockfile.write(str(os.getpid()))
        lockfile.flush()

        # Keep the file open for the process lifetime
        # The lock will automatically be released when the process exits
        # Store in global to prevent garbage collection
        global _lockfile_handle
        _lockfile_handle = lockfile

        logger.debug(f"Acquired singleton lock: {lockfile_path}")

    except IOError:
        # Lock is already held by another process
        print("Another talktype instance is already running. Exiting.", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Warning: could not acquire singleton lock: {e}", file=sys.stderr)

# Global to keep lock file open
_lockfile_handle = None

# --- Runtime state ---
SAMPLE_RATE = 16000
CHANNELS = 1
MIN_HOLD_MS = 200
START_BEEP = (1200, 0.12)
CANCEL_BEEP = (500, 0.12)
READY_BEEP  = (1000, 0.09)

@dataclass
class RecordingState:
    """Encapsulates mutable state for recording sessions."""
    is_recording: bool = False
    was_cancelled: bool = False
    frames: list = None
    stream: object = None
    press_t0: float = None
    # Hotkey testing state
    hold_key_tested: bool = False
    toggle_key_tested: bool = False
    hotkey_test_start_time: float = None

    def __post_init__(self):
        if self.frames is None:
            self.frames = []

# Global recording state
state = RecordingState()

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
    if state.is_recording:
        state.frames.append(indata.tobytes())

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
    state.frames = []
    state.was_cancelled = False
    state.is_recording = True
    state.press_t0 = time.time()
    sd.default.channels = CHANNELS
    sd.default.samplerate = SAMPLE_RATE
    state.stream = sd.InputStream(callback=_sd_callback, dtype='int16', device=input_device_idx)
    state.stream.start()
    print("🎙️  Recording…")
    logger.debug("Recording started")
    _beep(beeps_on, *START_BEEP)
    if notify_on: _notify("TalkType", "Recording… (speak now)")

def _stop_stream_safely():
    if state.stream:
        try:
            state.stream.stop(); state.stream.close()
        except Exception:
            pass
        state.stream = None

def cancel_recording(beeps_on: bool, notify_on: bool, reason="Cancelled"):
    state.is_recording = False
    state.was_cancelled = True
    _stop_stream_safely()
    _beep(beeps_on, *CANCEL_BEEP)
    print(f"⏸️  {reason}")
    logger.debug(f"Recording cancelled: {reason}")
    if notify_on: _notify("TalkType", reason)

def _send_shift_enter():
    """Send Shift+Enter keystrokes to create line break without submitting."""
    if shutil.which("ydotool"):
        try:
            env = os.environ.copy()
            runtime = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            env.setdefault("YDOTOOL_SOCKET", os.path.join(runtime, ".ydotool_socket"))
            # KEY_LEFTSHIFT (42), KEY_ENTER (28)
            subprocess.run(["ydotool", "key", "42:1", "28:1", "28:0", "42:0"], check=False, env=env)
            return True
        except Exception as e:
            logger.debug(f"ydotool shift+enter failed: {e}")
    return False

def _send_enter():
    """Send Enter keystroke to create a new line."""
    if shutil.which("ydotool"):
        try:
            env = os.environ.copy()
            runtime = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            env.setdefault("YDOTOOL_SOCKET", os.path.join(runtime, ".ydotool_socket"))
            # KEY_ENTER (28)
            subprocess.run(["ydotool", "key", "28:1", "28:0"], check=False, env=env)
            return True
        except Exception as e:
            logger.debug(f"ydotool enter failed: {e}")
    return False

def _type_text(text: str):
    # Handle special markers first
    if "§SHIFT_ENTER§" in text:
        parts = text.split("§SHIFT_ENTER§")
        for i, part in enumerate(parts):
            if part:  # Type the text part
                _type_text_raw(part)
            if i < len(parts) - 1:  # Not the last part, send Shift+Enter
                time.sleep(0.05)  # Small delay between text and key
                _send_shift_enter()
                time.sleep(0.05)  # Small delay after key
        return
    
    # Handle regular newlines by converting them to Enter key presses
    if "\n" in text:
        parts = text.split("\n")
        for i, part in enumerate(parts):
            if part:  # Type the text part
                _type_text_raw(part)
            if i < len(parts) - 1:  # Not the last part, send Enter
                time.sleep(0.05)  # Small delay between text and key
                _send_enter()
                time.sleep(0.05)  # Small delay after key
        return
    
    # Normal text typing
    _type_text_raw(text)

def _type_text_raw(text: str):
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
            logger.debug(f"ydotool failed: {e}")
    if shutil.which("wtype"):
        subprocess.run(["wtype", "--", text], check=False); return
    if shutil.which("wl-copy"):
        try:
            import pyperclip
            pyperclip.copy(text)
            print("📋 Copied to clipboard. Ctrl+V to paste.")
            logger.info("Text copied to clipboard (fallback mode)")
            return
        except Exception:
            pass
    logger.error("Could not type text: no ydotool/wtype/wl-copy available")
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
    held_ms = int((time.time() - (state.press_t0 or time.time())) * 1000)
    if held_ms < MIN_HOLD_MS:
        cancel_recording(beeps_on, notify_on, f"Cancelled (held {held_ms} ms)"); return
    state.is_recording = False
    _stop_stream_safely()
    if state.was_cancelled: return

    print("🛑 Recording stopped. Transcribing…")
    logger.debug("Recording stopped, starting transcription")
    # Convert captured bytes -> float32 mono PCM in [-1, 1]
    try:
        pcm_int16 = np.frombuffer(b''.join(state.frames), dtype=np.int16)
        if pcm_int16.size == 0:
            print("ℹ️  (No audio captured)")
            logger.debug("No audio captured during recording")
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
        logger.debug(f"Raw transcription: {raw!r}")
        text = normalize_text(raw if smart_quotes else raw.replace(""","\"").replace(""","\""))

        # Simple spacing: always add period+space or just space when auto features are on
        # Don't add auto-period or auto-space if text ends with special markers (like §SHIFT_ENTER§)
        if auto_period and text and not text.rstrip().endswith((".","?","!","…")) and not text.endswith("§"):
            text = text.rstrip() + "."
        if auto_space and text and not text.endswith((" ", "\n", "\t", "§")):
            text = text + " "
        print(f"📜 Text: {text!r}")
        logger.debug(f"Normalized text: {text!r}")

        _beep(beeps_on, *READY_BEEP)
        if notify_on: _notify("TalkType", f"Transcribed: {text[:80]}{'…' if len(text)>80 else ''}")
        if text:
            # Small settling delay so focused app is ready to receive text
            time.sleep(0.12)
            # Choose injection mode: paste entire utterance vs keystroke typing
            use_paste = paste_injection or os.environ.get("DICTATE_INJECTION_MODE","type").lower()=="paste"
            if use_paste and _paste_text(text):
                print(f"✂️  Inject (paste) len={len(text)}")
                logger.debug(f"Text injected via paste: {len(text)} chars")
            else:
                print(f"⌨️  Inject (type) len={len(text)}")
                logger.debug(f"Text injected via typing: {len(text)} chars")
                _type_text(text)
        else:
            print("ℹ️  (No speech recognized)")
            logger.debug("No speech recognized in audio")
    except Exception as e:
        logger.error(f"Transcription error: {e}", exc_info=True)
        print(f"❌ Transcription error: {e}")
        _beep(beeps_on, *READY_BEEP)  # Still play the ready beep so user knows it's done
        if notify_on: _notify("TalkType", f"Transcription failed: {str(e)[:60]}{'…' if len(str(e))>60 else ''}")

def _loop_evdev(cfg: Settings, input_device_idx):
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    print(f"Session: {session} | Wayland={session=='wayland'}")
    logger.info(f"Session type: {session}, Wayland: {session=='wayland'}")
    mode = cfg.mode.lower().strip()
    print(f"Mode: {mode} | Hold key: {cfg.hotkey}" + (f" | Toggle key: {cfg.toggle_hotkey}" if mode=='toggle' else ""))
    logger.info(f"Input mode: {mode}, Hold key: {cfg.hotkey}, Toggle key: {cfg.toggle_hotkey if mode=='toggle' else 'N/A'}")

    # Auto-timeout setup
    timeout_enabled = getattr(cfg, 'auto_timeout_enabled', False)
    timeout_minutes = getattr(cfg, 'auto_timeout_minutes', 5)
    timeout_seconds = timeout_minutes * 60
    last_activity_time = time.time()
    print(f"Auto-timeout: {timeout_enabled} | Timeout: {timeout_minutes} minutes")
    logger.info(f"Auto-timeout: enabled={timeout_enabled}, minutes={timeout_minutes}")

    devices = [InputDevice(p) for p in list_devices()]
    for dev in devices:
        try: dev.set_nonblocking(True)
        except Exception: pass

    hold_key = _keycode_from_name(cfg.hotkey)
    toggle_key = _keycode_from_name(cfg.toggle_hotkey) if mode == "toggle" else None

    # Initialize hotkey testing
    state.hotkey_test_start_time = time.time()
    state.hold_key_tested = False
    state.toggle_key_tested = False

    # Show hotkey verification dialog
    print(f"🎹 Showing hotkey verification dialog...")
    logger.info(f"Showing hotkey verification dialog for user")

    # Run dialog directly (GTK must run in main thread)
    action, verified = show_hotkey_test_dialog(mode, cfg.hotkey, cfg.toggle_hotkey)

    if action == "verified" and verified:
        state.hold_key_tested = True
        if mode == "toggle":
            state.toggle_key_tested = True
        print(f"✓ Hotkeys verified successfully")
        logger.info(f"Hotkeys verified by user")

        # Show final "Ready!" message
        try:
            gi.require_version('Gtk', '3.0')
            from gi.repository import Gtk

            ready_dialog = Gtk.MessageDialog(
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="✓ Hotkeys Verified!"
            )
            ready_dialog.format_secondary_text(
                "Your hotkeys are working correctly!\n\n"
                "The dictation service is now ready.\n"
                "Press F8 or F9 to start dictating."
            )
            ready_dialog.set_position(Gtk.WindowPosition.CENTER)
            ready_dialog.run()
            ready_dialog.destroy()
        except Exception as e:
            logger.error(f"Failed to show ready dialog: {e}")
    elif action == "change_keys":
        print("🔧 User wants to change hotkeys - opening Preferences...")
        logger.info("Opening Preferences for hotkey change")
        # Launch preferences
        try:
            src_dir = os.path.dirname(__file__)
            usr_dir = os.path.dirname(os.path.dirname(src_dir))
            prefs_script = os.path.join(usr_dir, "bin", "dictate-prefs")
            if os.path.exists(prefs_script):
                subprocess.Popen([prefs_script])
            else:
                subprocess.Popen([sys.executable, "-m", "talktype.prefs"])
        except Exception as e:
            logger.error(f"Failed to open Preferences: {e}")
        # Exit service so user can change keys and restart
        print("Service will exit. Please change your hotkeys and restart.")
        sys.exit(0)
    else:
        print("⚠️ Hotkey verification skipped by user")
        logger.warning("Hotkey verification skipped")

    while True:
        current_time = time.time()

        # Check for auto-timeout
        if timeout_enabled and not state.is_recording:
            if current_time - last_activity_time > timeout_seconds:
                print(f"⏰ Auto-timeout: No activity for {timeout_minutes} minutes, shutting down...")
                if cfg.notify:
                    _notify("TalkType Auto-Timeout", f"Service stopped after {timeout_minutes} minutes of inactivity")
                sys.exit(0)

        for dev in devices:
            try:
                for event in dev.read():
                    if event.type == ecodes.EV_KEY:
                        if mode == "hold":
                            if event.code == hold_key:
                                # Reset timeout timer only when TalkType hotkey is used
                                if timeout_enabled:
                                    last_activity_time = current_time
                                if event.value == 1 and not state.is_recording:
                                    start_recording(cfg.beeps, cfg.notify, input_device_idx)
                                elif event.value == 0 and state.is_recording:
                                    stop_recording(cfg.beeps, cfg.smart_quotes, cfg.notify, cfg.language, cfg.auto_space, cfg.auto_period, cfg.paste_injection)
                        else:  # toggle mode: press to start, press again to stop
                            if event.code == toggle_key and event.value == 1:
                                # Reset timeout timer only when TalkType hotkey is used
                                if timeout_enabled:
                                    last_activity_time = current_time
                                if not state.is_recording:
                                    start_recording(cfg.beeps, cfg.notify, input_device_idx)
                                else:
                                     stop_recording(cfg.beeps, cfg.smart_quotes, cfg.notify, cfg.language, cfg.auto_space, cfg.auto_period, cfg.paste_injection)
                        # ESC cancels in any mode
                        if event.code == ecodes.KEY_ESC and state.is_recording and event.value == 1:
                            # Reset timeout timer when ESC is used to cancel
                            if timeout_enabled:
                                last_activity_time = current_time
                            cancel_recording(cfg.beeps, cfg.notify, "Cancelled by ESC")
            except BlockingIOError:
                pass
            except Exception:
                pass
        time.sleep(0.005)

def build_model(settings: Settings):
    compute_type = "float16" if settings.device.lower() == "cuda" else "int8"
    try:
        model = WhisperModel(
            settings.model,
            device=settings.device,
            compute_type=compute_type,
            cpu_threads=os.cpu_count() or 4
        )
        print(f"✅ Model loaded successfully on {settings.device.upper()}")
        logger.info(f"Model loaded: {settings.model} on {settings.device}")
        return model
    except Exception as e:
        if settings.device.lower() == "cuda":
            print(f"❌ CUDA failed: {e}")
            logger.error(f"CUDA error: {type(e).__name__}: {str(e)}")
            import traceback
            logger.debug("CUDA traceback:", exc_info=True)
            print("🔄 Falling back to CPU...")
            try:
                model = WhisperModel(
                    settings.model,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=os.cpu_count() or 4
                )
                print("✅ Model loaded successfully on CPU (fallback)")
                logger.info("Model loaded on CPU (fallback from CUDA)")
                return model
            except Exception as cpu_e:
                print(f"❌ CPU fallback also failed: {cpu_e}")
                logger.error(f"CPU fallback failed: {cpu_e}")
                raise cpu_e
        else:
            print(f"❌ Model loading failed: {e}")
            logger.error(f"Model loading failed: {e}")
            raise e

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
    logger.info(f"Configuration: model={cfg.model}, device={cfg.device}, language={cfg.language or 'auto'}, auto_space={cfg.auto_space}, auto_period={cfg.auto_period}")
    _loop_evdev(cfg, input_device_idx)

if __name__ == "__main__":
    main()

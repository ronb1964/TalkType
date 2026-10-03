"""
Whisper on any graphics card, through Vulkan.

TalkType's usual Whisper engine (faster-whisper / CTranslate2) can only use
NVIDIA graphics, through CUDA. This runs whisper.cpp built with its Vulkan
backend instead, which works on AMD, Intel and NVIDIA alike. For AMD and
Intel it's the only way to use the graphics chip. For NVIDIA it's the light
option: measured on an RTX 4070 Super it matched CUDA's speed (large-v3,
0.51 s vs 0.53 s for 11 s of speech) for a 24 MB download instead of 1.4 GB. whisper.cpp
publishes no Linux Vulkan build, so TalkType builds one (build-vulkan-engine.sh)
and hosts it as a GitHub pre-release.

Nothing here is downloaded unless the user picks "Vulkan (any GPU)" as the
device: the engine (~24 MB) and the model in whisper.cpp's own format, which
is a separate file from the faster-whisper one.

whisper.cpp 1.9.4 also runs Parakeet (libparakeet), so the same engine runs
Parakeet on the graphics chip: 0.17 s instead of 2.15 s for 66 s of speech on
an RTX 4070 Super (2026-10-03). That runs as its own helper process,
parakeet_gpu.py, because whisper-server only serves Whisper models.

At run time it is a whisper-server process, started and watched the same way
as the AI cleanup engine (engine_process.py): it dies with the dictation
service and leftovers from a crash are cleaned up. Each dictation is sent to
it over 127.0.0.1 as a WAV.

Not every graphics chip is faster than the processor. A desktop Ryzen 7000's
built-in graphics has 2 compute units and measured no faster than its own
CPU, so speed_check() times both before the user switches.
"""
import glob
import io
import json
import os
import re
import shutil
import socket
import subprocess
import tarfile
import threading
import time
import urllib.request
import uuid
import wave

import numpy as np

from . import engine_process
from .logger import setup_logger
from .parakeet_engine import PARAKEET_MODEL, is_parakeet

logger = setup_logger(__name__)

DEVICE = "vulkan"   # the config value for this device
DEVICE_LABEL = "Vulkan (any GPU)"       # Preferences' Device dropdown
MENU_LABEL = "GPU (Vulkan)"             # "Device:" line in the tray and GNOME menus

# --- The engine download ------------------------------------------------------

ENGINE_VERSION = "1.9.4"                           # whisper.cpp release it is built from
# Build 2 adds Parakeet (libparakeet.so, parakeet-cli). It gets its own asset
# and pre-release: 0.12.0 to 0.13.1 download build 1 and check its SHA256, so
# build 1 must stay exactly as published. The folder inside keeps the old
# name, so build 2 unpacks over build 1 as a superset.
ENGINE_BUILD = 2
ENGINE_NAME = f"talktype-whisper-vulkan-{ENGINE_VERSION}"
ENGINE_ASSET = f"{ENGINE_NAME}-b{ENGINE_BUILD}-x64.tar.gz"
ENGINE_TAG = f"whisper-vulkan-{ENGINE_VERSION}-b{ENGINE_BUILD}"     # TalkType GitHub pre-release
ENGINE_URL = f"https://github.com/ronb1964/TalkType/releases/download/{ENGINE_TAG}/{ENGINE_ASSET}"
# From build-vulkan-engine.sh's .sha256; the download is refused if it doesn't
# match, so a tampered or truncated engine is never run.
ENGINE_SHA256 = "deb77b2912a90a584ecdec1017f14e75d0037ca78db601f030017a66f7b10b92"
ENGINE_SIZE_TEXT = "24 MB"

# --- Models, in whisper.cpp's format -------------------------------------------
# Quantized: about half the download, and less graphics memory, which matters
# on built-in graphics that share the computer's RAM. q8_0 for the small models
# (no accuracy cost worth measuring), q5_0 for the big ones.

MODEL_REPO = "ggerganov/whisper.cpp"
MODEL_FILES = {
    "tiny": ("ggml-tiny-q8_0.bin", "42 MB"),
    "base": ("ggml-base-q8_0.bin", "78 MB"),
    "small": ("ggml-small-q8_0.bin", "252 MB"),
    "medium": ("ggml-medium-q5_0.bin", "514 MB"),
    "large-v3": ("ggml-large-v3-q5_0.bin", "1 GB"),
    # q8_0, the same size as the processor's int8 download, and slightly
    # more accurate: 3.65% word errors vs 4.35% on LibriSpeech (2026-10-03).
    PARAKEET_MODEL: ("ggml-parakeet-tdt-0.6b-v3-q8_0.bin", "669 MB"),
}
# Models not hosted in whisper.cpp's own repo.
MODEL_REPOS = {PARAKEET_MODEL: "ggml-org/parakeet-GGUF"}


def supports_model(model_name) -> bool:
    """Whether *model_name* can run on the graphics chip through Vulkan."""
    return model_name in MODEL_FILES


def model_repo(model_name):
    """Hugging Face repo holding *model_name*'s whisper.cpp file."""
    return MODEL_REPOS.get(model_name, MODEL_REPO)


# --- Is there a graphics chip? -------------------------------------------------

AMD_VENDOR, INTEL_VENDOR, NVIDIA_VENDOR = "0x1002", "0x8086", "0x10de"


def graphics_vendors(drm_root="/sys/class/drm"):
    """PCI vendor ids of the graphics chips the kernel drives."""
    vendors = set()
    for vendor_file in glob.glob(os.path.join(drm_root, "card*", "device", "vendor")):
        try:
            with open(vendor_file) as f:
                vendors.add(f.read().strip().lower())
        except OSError:
            continue
    return vendors


def vulkan_available() -> bool:
    """Whether the system has the Vulkan loader (part of every desktop's
    graphics drivers; the engine can't run without it)."""
    import ctypes
    try:
        ctypes.CDLL("libvulkan.so.1")
        return True
    except OSError:
        return False


def is_offered() -> bool:
    """Show "Vulkan (any GPU)" as a device choice? Any AMD, Intel or NVIDIA
    chip with a Vulkan driver (NVIDIA's own driver includes one)."""
    vendors = graphics_vendors()
    return bool(vendors & {AMD_VENDOR, INTEL_VENDOR, NVIDIA_VENDOR}) and vulkan_available()


def has_nvidia() -> bool:
    return NVIDIA_VENDOR in graphics_vendors()


# --- Where things live ---------------------------------------------------------

def _engine_dir():
    from .config import get_data_dir
    return os.path.join(get_data_dir(), "whisper-vulkan", ENGINE_VERSION, ENGINE_NAME)


def _binary(name):
    return os.path.join(_engine_dir(), name)


def is_engine_installed(model_name=None) -> bool:
    """The engine is downloaded, and can run *model_name* if one is given.
    Build 1 has no Parakeet in it but still serves every Whisper model."""
    if not os.access(_binary("whisper-server"), os.X_OK):
        return False
    return not is_parakeet(model_name) or os.access(_binary("parakeet-cli"), os.X_OK)


def model_path(model_name):
    """Local path of the whisper.cpp model for *model_name*, or None."""
    if not supports_model(model_name):
        return None
    try:
        from huggingface_hub import hf_hub_download
        return hf_hub_download(model_repo(model_name), MODEL_FILES[model_name][0],
                               local_files_only=True)
    except Exception:
        return None


def is_installed(model_name) -> bool:
    """Engine and this model's whisper.cpp file are both downloaded."""
    return is_engine_installed(model_name) and model_path(model_name) is not None


def make_engine_download_func(model_name=None):
    """DownloadTask function: fetch, verify and unpack the engine, unless the
    one already there can run *model_name*."""
    def download(progress_callback, cancel_event):
        from .download_utils import download_file
        if is_engine_installed(model_name):
            progress_callback("Already downloaded", 100)
            return True
        parent = os.path.dirname(_engine_dir())
        os.makedirs(parent, exist_ok=True)
        archive = os.path.join(parent, ENGINE_ASSET)

        def hook(done, total):
            if total:
                progress_callback("Downloading graphics engine...", min(95, int(done * 95 / total)))

        if not download_file(ENGINE_URL, archive, timeout=60, cancel_event=cancel_event,
                             progress_hook=hook, expected_sha256=ENGINE_SHA256):
            progress_callback("Download failed", 0)
            return False
        try:
            progress_callback("Unpacking...", 97)
            staging = parent + ".unpacking"
            shutil.rmtree(staging, ignore_errors=True)
            with tarfile.open(archive) as tar:
                if hasattr(tarfile, "data_filter"):
                    tar.extractall(staging, filter="data")   # refuses unsafe paths
                else:
                    tar.extractall(staging)
            target = _engine_dir()
            shutil.rmtree(target, ignore_errors=True)
            os.replace(os.path.join(staging, ENGINE_NAME), target)
            shutil.rmtree(staging, ignore_errors=True)
            os.remove(archive)
        except Exception as e:
            logger.error(f"Could not unpack the graphics engine: {e}")
            progress_callback("Could not unpack the download", 0)
            return False
        progress_callback("Done", 100)
        return True
    return download


def make_model_download_func(model_name):
    """DownloadTask function: fetch *model_name*'s whisper.cpp file."""
    from .model_helper import make_model_download_func as _hf_download
    return _hf_download(f"whisper-vulkan-{model_name}", repo_id=model_repo(model_name),
                        only_files=(MODEL_FILES[model_name][0],))


# --- Which graphics chip -------------------------------------------------------

_DEVICE_LINE = re.compile(r"ggml_vulkan: (\d+) = (.+?) \| uma: (\d)")


def parse_vulkan_devices(output):
    """[(index, name, is_nvidia, is_integrated)] from the device list the
    engine prints when it starts."""
    devices = []
    for index, name, uma in _DEVICE_LINE.findall(output):
        devices.append((int(index), name.strip(), "nvidia" in name.lower(), uma == "1"))
    return devices


def choose_device(devices):
    """The graphics chip to use: a separate graphics card (any brand) before
    one built into the processor, which is far smaller. On a machine with an
    NVIDIA card and a Ryzen's built-in Radeon, that's the NVIDIA card: 16x
    faster than the processor, where the built-in chip was no faster at all.
    None if there is no graphics chip."""
    if not devices:
        return None
    return sorted(devices, key=lambda d: d[3])[0][0]     # discrete (uma 0) first, stable


def _engine_env():
    return {**os.environ, "LD_LIBRARY_PATH": _engine_dir()}


def find_device():
    """Index of the graphics chip the engine should use, or None."""
    try:
        out = subprocess.run([_binary("whisper-server"), "--help"], capture_output=True,
                             text=True, timeout=30, env=_engine_env()).stderr
    except Exception as e:
        logger.warning(f"Could not list graphics devices: {e}")
        return None
    devices = parse_vulkan_devices(out)
    logger.info(f"Vulkan devices: {devices}")
    return choose_device(devices)


# --- The speed check -----------------------------------------------------------

_TOTAL_TIME = re.compile(r"total time =\s+([\d.]+) ms")
_LOAD_TIME = re.compile(r"load time =\s+([\d.]+) ms")


def _time_one(model, extra_args, threads, cli="whisper-cli"):
    out = subprocess.run(
        [_binary(cli), "-m", model, "-f", _binary("speed-check.wav"),
         "-t", str(threads), *extra_args],
        capture_output=True, text=True, timeout=300, env=_engine_env())
    found = _TOTAL_TIME.search(out.stderr)
    if out.returncode != 0 or not found:
        raise RuntimeError(f"speed check run failed (exit {out.returncode})")
    seconds = float(found.group(1)) / 1000
    if cli == "parakeet-cli":
        # Parakeet transcribes the sample in a few hundredths of a second on a
        # graphics card, so loading the model (0.2 s there, 0.08 s on the
        # processor) would swamp the comparison. The service loads it once.
        load = _LOAD_TIME.search(out.stderr)
        if load:
            seconds -= float(load.group(1)) / 1000
    return seconds


def speed_check(model_name, device_index, threads=None):
    """Seconds to transcribe the 11-second sample on the graphics chip and on
    the processor, as (graphics, processor). The graphics run is done twice
    and the second one counted: the first pays one-time shader setup."""
    threads = threads or max(1, (os.cpu_count() or 2) // 2)
    model = model_path(model_name)
    cli = "parakeet-cli" if is_parakeet(model_name) else "whisper-cli"
    gpu_args = ["-dev", str(device_index)]
    _time_one(model, gpu_args, threads, cli)
    gpu = _time_one(model, gpu_args, threads, cli)
    cpu = _time_one(model, ["-ng"], threads, cli)
    logger.info(f"Speed check ({model_name}): graphics {gpu:.2f}s, processor {cpu:.2f}s")
    return gpu, cpu


def graphics_is_worth_it(gpu_seconds, cpu_seconds) -> bool:
    """Use the graphics chip only when it is clearly faster: at least 20%,
    so a near tie doesn't swap the processor for an extra background engine."""
    return gpu_seconds * 1.2 <= cpu_seconds


# --- Talking to the engine -----------------------------------------------------

def wav_bytes(audio_f32, sample_rate=16000):
    """16-bit mono WAV of float32 audio in [-1, 1], in memory."""
    pcm = (np.clip(audio_f32, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def multipart(fields, file_bytes):
    """(body, content type) of a multipart form with *fields* and one file."""
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                     f'{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                 f'filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
                 + file_bytes + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


# whisper.cpp writes non-speech as bracketed markers: silence or room noise
# with a language set came back as the text "[BLANK_AUDIO]", which would have
# been typed. Any all-caps bracketed tag is such a marker, never dictation.
_MARKER = re.compile(r"\[[A-Z][A-Z _]*\]")


def parse_result(reply):
    """(text, highest no-speech probability) from a verbose_json reply, with
    whisper.cpp's non-speech markers removed.

    The no-speech probability is reported but not to be trusted: measured on
    the same audio it read 0.90 for clear speech with the language set and
    0.00 for pure silence (2026-10-03), so the service doesn't use it."""
    segments = reply.get("segments") or []
    text = " ".join((s.get("text") or "").strip() for s in segments).strip()
    if not segments:
        text = (reply.get("text") or "").strip()
    text = " ".join(_MARKER.sub(" ", text).split())
    no_speech = max((float(s.get("no_speech_prob", 0.0)) for s in segments), default=0.0)
    return text, no_speech


class VulkanWhisperModel:
    """A whisper-server process running *model_name* on graphics chip
    *device_index*, kept running for the life of the dictation service."""

    def __init__(self, model_name, device_index, threads=None):
        self.model_name = model_name
        self.device_index = device_index
        self.threads = threads or max(1, (os.cpu_count() or 2) // 2)
        self._proc = None
        self._port = None
        # Re-entrant: a restart inside transcribe() runs a warm-up transcribe().
        self._lock = threading.RLock()
        self._start()

    def _start(self):
        engine_process.kill_orphans(engine_process.processes_of(_binary("whisper-server")),
                                    engine_process.is_talktype_process, "graphics engine")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self._port = s.getsockname()[1]
        self._proc = subprocess.Popen(
            [_binary("whisper-server"), "-m", model_path(self.model_name),
             "--host", "127.0.0.1", "--port", str(self._port),
             "-t", str(self.threads), "-dev", str(self.device_index)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_engine_env(),
            preexec_fn=engine_process.set_parent_death_signal)
        logger.info(f"Graphics engine starting (pid {self._proc.pid}, device {self.device_index})")
        deadline = time.time() + 120
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError("the graphics engine stopped while starting")
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self._port}/health", timeout=1)
                break
            except Exception:
                time.sleep(0.25)
        else:
            self.close()
            raise RuntimeError("the graphics engine did not start in time")
        # One short practice run: the first request on a graphics chip pays
        # one-time shader setup, which would otherwise land on the first dictation.
        started = time.time()
        self.transcribe(np.zeros(16000, dtype=np.float32), "en")
        logger.info(f"Graphics engine ready (warm-up took {time.time() - started:.1f}s)")

    def transcribe(self, audio_f32, language=None, timeout=120):
        """(text, highest no-speech probability) for *audio_f32*."""
        fields = {"response_format": "verbose_json", "temperature": "0.0",
                  "beam_size": "5", "language": language or "auto"}
        body, content_type = multipart(fields, wav_bytes(audio_f32))
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                logger.warning("Graphics engine had stopped; starting it again")
                self._start()
            request = urllib.request.Request(
                f"http://127.0.0.1:{self._port}/inference", data=body,
                headers={"Content-Type": content_type})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return parse_result(json.load(response))

    def close(self):
        proc, self._proc = self._proc, None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

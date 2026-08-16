# Flatpak GPU-in-sandbox spike — FINDINGS

**Date:** 2026-08-16 · **Host:** Nobara (Fedora 44 base), KDE Plasma, Wayland ·
**GPU:** RTX 4070 SUPER, driver 595.91.07 · **Runtime:** `org.gnome.Platform//48` (Python 3.12) ·
**Spec:** `docs/superpowers/specs/2026-08-16-flatpak-gpu-sandbox-spike-design.md`

## Bottom line

**Step A: PASS.** A Flatpak sandbox on this machine gets full NVIDIA driver + device access with
the *minimal* `--device=dri` permission — no `--device=all` needed. `libcuda.so.1` auto-mounts from
the NVIDIA GL extension on the default library path, `cuInit`/`cuDeviceGetCount` succeed, and the
card is named correctly from inside the sandbox. Step B (real GPU transcription) pending.

## Step A — driver-access gate (`gpu_probe.py`, `--device=dri`)

```
FLATPAK_ID=io.github.ronb1964.TalkTypeGpuProbe
LD_LIBRARY_PATH=
device nodes:
  /dev/nvidia0: present
  /dev/nvidiactl: present
  /dev/nvidia-uvm: present
  /dev/dri: present
loaded libcuda from: libcuda.so.1
cuDeviceGetCount = 1
cuDeviceGetName = NVIDIA GeForce RTX 4070 SUPER
RESULT: PASS — sandbox has NVIDIA driver + device access
```

### Facts for the real manifest
- **Device permission:** `--device=dri` is sufficient — the `/dev/nvidia0`, `/dev/nvidiactl`, and
  `/dev/nvidia-uvm` nodes (the ones CUDA compute needs) are all present with just `dri`. `--device=all`
  is NOT required. This is the minimal, Flathub-friendly setting.
- **libcuda:** supplied by the NVIDIA GL extension (`org.freedesktop.Platform.GL.nvidia-595-91-07`,
  auto-matched to the host driver) and resolves as `libcuda.so.1` on the default loader path — no
  `LD_LIBRARY_PATH` entry needed for the *driver* lib.
- **GPU detection:** `nvidia-smi` is absent in the sandbox (host binary). The ctypes `libcuda`
  probe works and is the recommended Flatpak-aware replacement for `cuda_helper.detect_nvidia_gpu`
  (alternative: `ctranslate2.get_cuda_device_count()` once ctranslate2 is bundled).

### CUDA toolkit libs available on host (for Step B / the manifest bundle list)
Under `~/.local/share/TalkType/cuda/lib/` (CUDA 12 / cuDNN 9):
- `cuda_runtime/lib/libcudart.so.12`
- `cublas/lib/libcublas.so.12`, `libcublasLt.so.12`
- `cudnn/lib/libcudnn.so.9` (+ cnn/ops/graph/engines sub-libs)

## Step B — real GPU transcription (`transcribe_probe.py`, `--device=dri`) — PASS

```
ctranslate2.get_cuda_device_count() = 1
WhisperModel loaded on device=cuda (no CPU fallback requested)
TRANSCRIPT: 'the quick brown fox jump over the lazy dog.'
RESULT: PASS — GPU transcription ran inside the Flatpak sandbox
```

**The spike goal is proven:** the real Whisper stack transcribes on the GPU from inside a Flatpak
on this machine, with no CPU fallback.

### Facts for the real manifest (Step B)
- **Python deps (pip into `/app` for Python 3.12, built with `org.gnome.Sdk//48`):**
  `faster-whisper 1.2.1` → pulls `ctranslate2 4.8.1`, `numpy 2.5.2`, `onnxruntime 1.28.0`,
  `av 18.1.0`, `tokenizers`, `huggingface-hub`, `tqdm`, etc. (~419 MB installed image). ctranslate2
  4.8.1 matches the host's **CUDA 12 / cuDNN 9** libs by soname — no version tweaking needed.
- **CUDA toolkit libs:** provided by putting these on `LD_LIBRARY_PATH` (order as shown):
  `…/cuda/lib/cudnn/lib : …/cuda/lib/cublas/lib : …/cuda/lib/cuda_runtime/lib`.
  In the spike they were mounted read-only from the host download; the real app keeps its existing
  download-on-demand into the app's data dir (`~/.var/app/<id>/data/...`) and points
  `LD_LIBRARY_PATH` there.
- **libcuda:** from the NVIDIA GL extension, default loader path (Step A) — nothing to bundle.
- **Runtime permissions used:** `--device=dri` only. No network needed at run time (model + libs
  local). ctranslate2's `get_cuda_device_count()` returns 1 in-sandbox — confirms it as the
  Flatpak GPU-detection method.
- **Audio I/O:** decoded the WAV with the stdlib `wave` module and passed faster-whisper a float32
  numpy array — no PyAV needed for the read path (though `av` is bundled as a faster-whisper dep).

## Net result → the Flatpak manifest project

Both sandbox unknowns are now settled fact:
- **Backend B (portal hotkey + libei typing):** proven by the portal spike (KDE).
- **GPU transcription:** proven here (KDE), with the exact permission (`--device=dri`), the CUDA
  `LD_LIBRARY_PATH` layout, the pip dependency set, and the `nvidia-smi` → ctypes/ctranslate2
  detection replacement all recorded.

The real Flatpak build has no remaining research risk — it is now assembly: a proper
`flatpak-builder` manifest bundling the Python deps, wiring download-on-demand CUDA into the app
data dir, adapting `detect_nvidia_gpu` for the sandbox, onboarding parity (desktop-assigned hotkey),
and KDE + GNOME end-to-end passes.


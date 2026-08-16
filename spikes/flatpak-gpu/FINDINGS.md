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

## Step B — real GPU transcription

_Pending — see `build_gpu_transcribe_flatpak.sh` / `transcribe_probe.py`._

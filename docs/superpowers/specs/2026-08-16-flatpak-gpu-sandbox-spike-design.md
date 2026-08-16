# Flatpak GPU-in-sandbox spike — design

**Date:** 2026-08-16 · **Status:** approved (brainstorm) · **Type:** throwaway de-risking spike
**Host:** Nobara (Fedora 44 base), KDE Plasma, Wayland · **GPU:** RTX 4070 SUPER, driver 595.91.07

## Why this spike exists

The real deliverable is a **self-hosted, direct-download Flatpak** of TalkType that operates
exactly like the AppImage — including its "detect NVIDIA card → offer the ~1.4GB CUDA download →
transcribe on GPU" flow. Distribution is self-hosted first (Flathub later), so the AppImage's
download-CUDA-on-demand model can carry over unchanged.

Every part of that build is well-understood work **except one unknown**: whether GPU transcription
works at all from inside a Flatpak sandbox. If it does, we build the real Flatpak for full parity
with confidence. If it doesn't, the whole "not slower than the other versions" goal is at risk and we
need to know before investing in the manifest. This spike answers that one question cheaply, the same
way the portal-input spike retired the hotkey/typing risk before Backend B was built.

## Goal & success criteria

**One question, answered yes/no with evidence:** *Can TalkType run Whisper transcription on the
`cuda` device from inside a Flatpak sandbox on this machine?*

**Success =** a Whisper transcription runs on `device="cuda"` inside a throwaway Flatpak
(`org.gnome.Platform//48`) and returns text, using the host's already-downloaded CUDA libraries
(`~/.local/share/TalkType/cuda`) plus the driver's `libcuda.so` supplied by the Flatpak NVIDIA GL
extension — **with no CPU fallback**. Plus a written record of:

1. the exact `finish-args` / device permissions that granted GPU access,
2. where `libcuda.so` and the CUDA runtime libs resolve from inside the sandbox, and any
   `LD_LIBRARY_PATH` needed,
3. a **Flatpak-aware GPU-detection method** to replace `nvidia-smi` (which is a host binary and is
   expected to be absent in the sandbox).

## Non-goals (explicitly out of scope for the spike)

- The real Flatpak manifest, `flatpak-builder`, dependency bundling for the whole app, onboarding,
  recording indicator, model-download UI, KDE/GNOME UX parity — all belong to the follow-on
  **Flatpak manifest project**, informed by this spike's findings.
- GNOME cross-check of GPU (do it in the manifest project's VM passes; this spike is host-KDE only).
- CPU transcription — already proven working everywhere; not re-tested here.
- Flathub packaging rules — deferred with distribution.

## Approach — two steps, cheap before expensive

Answer the hard part (driver access) first with almost no setup; only do the heavier
transcription proof if that passes.

### Step A — driver-access gate (minutes, nothing to bundle)

A throwaway Flatpak on `org.gnome.Platform//48` running a **pure-`ctypes` probe** against
`libcuda.so` — the no-dependency trick that cracked libei. The probe calls
`cuInit(0)` → `cuDeviceGetCount(&n)` → `cuDeviceGetName(...)` and prints the device name.

- Device access: start with `--device=dri`; if `cuDeviceGetCount` returns 0 or `cuInit` fails,
  retry with `--device=all` (CUDA needs the `/dev/nvidia*` + `/dev/nvidia-uvm` nodes, which
  `--device=dri` may not expose). **Record which one worked** — the real manifest will use the
  minimal set that succeeds.
- The NVIDIA GL extension (`org.freedesktop.Platform.GL.nvidia-595-91-07`, already installed) is
  expected to auto-mount and provide `libcuda.so` under `/usr/lib/$ARCH/GL/nvidia/lib/`. If the
  probe can't find `libcuda.so.1`, add that dir to `LD_LIBRARY_PATH` in the launcher and record it.
- **Set `restype`/`argtypes` on every libcuda call** (same 64-bit-pointer-truncation trap the libei
  spike documented) or pointers silently corrupt and segfault.

Printing "RTX 4070 SUPER" from inside the sandbox proves the sandbox can see and initialize the GPU —
the entire risk. A failure here is a cheap, early, decisive answer.

### Step B — real transcription proof (only if A passes)

Add just enough to run the actual stack inside the sandbox:

- Bundle `faster-whisper` (which pulls `ctranslate2`) for the runtime's **Python 3.12** by
  `pip install --prefix=/app` from `org.gnome.Sdk//48` at build time, and set `PYTHONPATH`.
  *(Installing `org.gnome.Sdk//48` is a prerequisite download — see Risks.)*
- Provide the CUDA runtime libraries by mounting/copying the host's existing
  `~/.local/share/TalkType/cuda` and putting its `lib/` on `LD_LIBRARY_PATH` (alongside the
  driver's `libcuda.so` from Step A). This mirrors exactly how the AppImage loads CUDA — no
  re-download of 1.4GB.
- Run `WhisperModel(<small/base cached model>, device="cuda", compute_type="float16")
  .transcribe(<short cached WAV>, vad_filter=False)` and print the text.

**Acceptance:** text returned, and the run used the GPU (assert no "falling back to CPU" and,
if available, `ctranslate2.get_cuda_device_count() > 0`). Point at a `base`-size Whisper model
already in the host cache with `local_files_only=True` (faster-whisper caches are already in
ctranslate2 format — no conversion needed) so the spike needs no network.

## Deliverables

Everything lands in a new throwaway dir `spikes/flatpak-gpu/`, disposable like `spikes/flatpak-portal/`:

- `gpu_probe.py` — the Step A ctypes libcuda probe.
- `build_gpu_probe_flatpak.sh` — build-init/finish/export/install of the Step A probe (no builder).
- `transcribe_probe.py` — the Step B GPU transcription probe.
- `build_gpu_transcribe_flatpak.sh` — Step B build (adds ctranslate2/faster-whisper via Sdk 48 pip
  + CUDA libs + cached model).
- `FINDINGS.md` — the yes/no answer plus the three recorded facts above, written to directly seed
  the real Flatpak manifest project. Mirrors the structure of the portal spike's FINDINGS.

## Risks & open questions

- **`--device=all` vs `--device=dri`.** CUDA typically needs the nvidia device nodes; `--device=all`
  is the likely-required setting. The manifest will want the *minimal* permission that works — the
  spike records it. (`--device=all` is broad; if it's required, note it as a Flathub-review
  consideration for the deferred Flathub goal.)
- **`org.gnome.Sdk//48` not yet installed** — Step B needs it to pip-build ctranslate2/faster-whisper
  for Python 3.12. One-time `flatpak install` (a download). Step A needs only the Platform.
- **CUDA lib ABI vs runtime glibc.** The downloaded CUDA libs and the `ctranslate2` manylinux wheel
  must load against the GNOME 48 runtime (freedesktop 24.08 base, modern glibc). Expected fine;
  the spike proves it.
- **`libcudnn`.** faster-whisper/ctranslate2 GPU needs cuDNN in addition to cudart/cublas. Confirm
  the host `~/.local/share/TalkType/cuda` set includes cuDNN (the AppImage download does); if not,
  that's a finding for the manifest's bundle list.
- **Detection replacement.** Candidates to test for the Flatpak-aware `detect_nvidia_gpu`:
  `ctypes` `libcuda` probe (as in Step A), `ctranslate2.get_cuda_device_count()`, or presence of
  `/dev/nvidia0`. The spike recommends one; wiring it into `cuda_helper.py` is manifest-project work.

## What this feeds

The FINDINGS become direct inputs to the **Flatpak manifest project** spec: the device-permission
set, the CUDA/`libcuda` load paths, the ctranslate2/CUDA bundle list (incl. cuDNN), and the
GPU-detection method — turning the biggest unknown into settled fact before the real build begins.

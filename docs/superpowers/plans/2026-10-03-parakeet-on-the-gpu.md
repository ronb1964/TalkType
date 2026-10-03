# Parakeet on the GPU (Vulkan) — plan

Research: Obsidian "TalkType/2026-10-03 - Parakeet on the GPU (research)".
On an RTX 4070 Super, whisper.cpp's libparakeet through Vulkan transcribed 66 s
in 0.17 s against 2.15 s for TalkType's ONNX CPU Parakeet, with no accuracy
loss (LibriSpeech dummy: WER 3.65% vs 4.35%).

## Decisions (Ron, 2026-10-03)
- **Follows Device.** Parakeet runs on the graphics chip when Device is
  "Vulkan (any GPU)"; no new setting. CUDA/CPU users keep the CPU engine.
- **Keep both model files.** The ONNX (CPU) download is never deleted; it is
  the fallback if the graphics helper fails.

## Design
1. **Engine build 2.** `build-vulkan-engine.sh <ver> [build]` also builds
   `parakeet-cli` (and so `libparakeet.so`). Asset
   `talktype-whisper-vulkan-1.9.4-b2-x64.tar.gz` under a NEW pre-release tag
   `whisper-vulkan-1.9.4-b2`; the folder inside keeps its old name, so it
   unpacks over the build-1 engine as a superset. Build 1 stays published
   untouched (0.12.0–0.13.1 verify its SHA256).
2. **whisper_vulkan.py**
   - `MODEL_FILES["parakeet-v3"]` = q8_0 GGUF (669 MB) from
     `ggml-org/parakeet-GGUF` (per-model repo).
   - `is_engine_installed(model)` also requires `libparakeet.so` for
     Parakeet; the engine download re-fetches when that piece is missing.
   - `speed_check` uses `parakeet-cli` for Parakeet (total minus load time).
3. **parakeet_gpu.py + parakeet_gpu_worker.py.** No Parakeet server exists
   upstream, and a GGML_ASSERT aborts its whole process, so the GPU engine is
   a separate helper process (`python -m talktype.parakeet_gpu_worker`) that
   loads libparakeet through ctypes and talks over stdin/stdout. It must call
   `ggml_backend_load_all_from_path` before loading (GGML_BACKEND_DL build).
   Warm-up run at start (first-ever GPU run compiles shaders, ~8 s). Dies with
   the service (PR_SET_PDEATHSIG). If it fails, recognize() falls back to the
   ONNX CPU model when that is downloaded.
4. **Wiring.** `effective_device()` says vulkan for Parakeet only when the
   GPU files are there. `build_model` builds the GPU helper for Parakeet on
   Vulkan; missing files → CPU silently (0.13.1 users with device=vulkan who
   use Parakeet must not get a warning on every start). The tray's
   Fast & Accurate preset keeps Vulkan users on Vulkan. Setup dialogs stop
   refusing Parakeet. Help/tooltips/README text updated.

## Release (needs Ron's OK)
Build engine b2, upload as pre-release `whisper-vulkan-1.9.4-b2`, put its
SHA256 in `ENGINE_SHA256`. Not part of any TalkType release until Ron says.

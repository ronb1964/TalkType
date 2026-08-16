# TalkType Flatpak (self-hosted) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a real, self-hosted `flatpak-builder` Flatpak of TalkType with AppImage parity,
including NVIDIA GPU transcription, built on `org.gnome.Platform//48`.

**Architecture:** Same source; packaging + the two `FLATPAK_ID`-gated seams (portal hotkey / libei
typing) differ. The manifest bundles what the GNOME runtime lacks (Python ML/audio stack, PortAudio,
AyatanaAppIndicator3) and the app branches on `FLATPAK_ID` for GPU detection and the updater.

**Tech Stack:** flatpak-builder, `org.gnome.Platform//48` + `org.gnome.Sdk//48`, Python 3.12,
faster-whisper/ctranslate2 (CUDA 12/cuDNN 9), Backend B (GlobalShortcuts + libei), PortAudio,
libayatana-appindicator3.

## Global Constraints

- **Backend A untouched.** Every app-code change is gated on `os.environ.get("FLATPAK_ID")`; the
  evdev+ydotool path must be byte-for-byte behaviorally unchanged. New unit tests follow the
  existing `tests/` pattern and run under the project test cmd.
- **Test cmd:** `PYTHONPATH=/usr/lib64/python3.14/site-packages:/usr/lib/python3.14/site-packages:src .venv/bin/python -m pytest -q`
- **App ID:** `io.github.ronb1964.TalkType`. **Runtime:** `org.gnome.Platform//48`. **Device perm:**
  `--device=dri` (proven sufficient). **GPU libs:** download-on-demand into the app data dir; CUDA
  `LD_LIBRARY_PATH` order `cudnn/lib:cublas/lib:cuda_runtime/lib`; `libcuda` from the NVIDIA GL
  extension.
- **Commit frequently**, one deliverable per commit, co-authored trailer.
- Manifest + helper scripts live in `packaging/flatpak/`. Throwaway spike code in `spikes/` is
  reference only — do not ship it.

---

## Phase 1 — Boot skeleton (the dependency bundle proves out)

Goal: `flatpak run io.github.ronb1964.TalkType` starts the tray + dictation service in the sandbox,
CPU-only, and the service reaches "Model loaded" after a model download. This proves the hardest
assembly piece — the full dependency bundle — before any UX work.

**Files:**
- Create: `packaging/flatpak/io.github.ronb1964.TalkType.yml` (flatpak-builder manifest)
- Create: `packaging/flatpak/build-flatpak.sh` (build + bundle wrapper, mirrors `build-release.sh`)
- Create: `packaging/flatpak/talktype-launcher` (in-sandbox entry: sets paths, runs `-m talktype.tray`)
- Reference: `pyproject.toml` (dep list), `spikes/flatpak-gpu/build_gpu_transcribe_flatpak.sh`
  (proven pip-into-/app pattern), `src/talktype/service_launcher.py` (how the service is spawned)

- [ ] **Step 1: Install flatpak-builder**

Run: `flatpak install --user -y flathub org.flatpak.Builder`
Verify: `flatpak run org.flatpak.Builder --version` prints a version.

- [ ] **Step 2: Write the manifest skeleton (runtime + app module only, no deps yet)**

`packaging/flatpak/io.github.ronb1964.TalkType.yml`:
```yaml
app-id: io.github.ronb1964.TalkType
runtime: org.gnome.Platform
runtime-version: '48'
sdk: org.gnome.Sdk
command: talktype-launcher
finish-args:
  - --socket=wayland
  - --socket=fallback-x11
  - --share=ipc
  - --socket=pulseaudio
  - --device=dri
  - --share=network
  - --talk-name=org.freedesktop.portal.Desktop
modules:
  - name: talktype
    buildsystem: simple
    build-commands:
      - install -Dm755 packaging/flatpak/talktype-launcher /app/bin/talktype-launcher
      - cp -r src/talktype /app/lib/talktype
      - install -Dm644 io.github.ronb1964.TalkType.appdata.xml
          /app/share/metainfo/io.github.ronb1964.TalkType.appdata.xml
    sources:
      - type: dir
        path: ../..
```

`packaging/flatpak/talktype-launcher`:
```sh
#!/bin/sh
export PYTHONPATH=/app/lib:/app/lib/python3.12/site-packages:$PYTHONPATH
exec python3 -m talktype.tray "$@"
```

- [ ] **Step 3: Add the Python dependency module (pip into /app)**

Add before the `talktype` module (proven in the GPU spike). Prefer pinned wheels for reproducibility;
start unpinned to get building, then pin:
```yaml
  - name: python-deps
    buildsystem: simple
    build-options:
      build-args: [--share=network]
    build-commands:
      - pip3 install --prefix=/app --no-warn-script-location
          faster-whisper sounddevice evdev pyperclip toml
```
Note: `--share=network` at build time requires `flatpak-builder --disable-rofiles-fuse` or building
with the network build-arg; if the builder blocks network, switch to a pinned `requirements.txt`
downloaded to sources. Record which worked in the manifest comment.

- [ ] **Step 4: Add PortAudio (sounddevice's native dep)**

```yaml
  - name: portaudio
    buildsystem: cmake-ninja
    config-opts: [-DCMAKE_BUILD_TYPE=Release]
    sources:
      - type: archive
        url: https://files.portaudio.com/archives/pa_stable_v190700_20210406.tgz
        sha256: 47efbf42c77c19a05d22e627d42873e991ec0c1357219c0d74ce6a2948cb2def
```
(Confirm the current stable URL+sha at build time; adjust if the mirror moved.)

- [ ] **Step 5: Add AyatanaAppIndicator3 (tray icon lib + GI typelib)**

```yaml
  - name: libdbusmenu-gtk3   # AppIndicator dependency, GTK3 variant
    # ... (build module — finalize source URL/sha during build)
  - name: libayatana-appindicator
    buildsystem: cmake-ninja
    config-opts: [-DENABLE_BINDINGS_MONO=NO, -DENABLE_BINDINGS_VALA=NO]
    sources:
      - type: git
        url: https://github.com/AyatanaIndicators/libayatana-appindicator.git
        tag: <pin a released tag during build>
```
(This module set is the main Phase-1 unknown; finalize exact deps/tags empirically, then pin.)

- [ ] **Step 6: Build**

Run: `./packaging/flatpak/build-flatpak.sh` (wraps
`flatpak run org.flatpak.Builder --user --install --force-clean build-dir
packaging/flatpak/io.github.ronb1964.TalkType.yml`).
Expected: build completes; app installs `--user`.

- [ ] **Step 7: Run and verify boot**

Run: `flatpak run io.github.ronb1964.TalkType`
Expected: tray icon appears; `flatpak run --command=cat ... ` of the in-sandbox log (or stderr)
shows the service importing cleanly (numpy/sounddevice/faster-whisper import OK) and, after choosing
a model, "Model loaded: <model> on cpu". No `ModuleNotFoundError`, no PortAudio/AppIndicator load
error.

- [ ] **Step 8: Commit**

```bash
git add packaging/flatpak/
git commit -m "flatpak: boot skeleton manifest — app starts in the sandbox (CPU)"
```

---

## Phase 2 — Backend B end-to-end on KDE

Goal: dictation works in the sandbox via the portal hotkey + libei typing; Backend A never runs.

- [ ] Assign the `dictate` shortcut in KDE System Settings; approve the one-time RemoteDesktop dialog.
- [ ] Hold the key, speak, release → text typed into a focused editor (KWrite).
- [ ] Confirm in the log: `PortalInputBackend`/`LibeiOutputBackend` selected (FLATPAK_ID set), evdev
      never grabbed.
- [ ] Decide + implement `restore_token` storage in the app data dir so the remote-control dialog is
      a one-time approval (add a `FLATPAK_ID`-gated test if it touches app code).
- [ ] Commit.

## Phase 3 — GPU parity

Goal: NVIDIA detected in-sandbox → CUDA download-on-demand into the app data dir → GPU transcription.

- [ ] TDD: `FLATPAK_ID`-gated GPU detection swap in `cuda_helper.detect_nvidia_gpu`
      (nvidia-smi → `ctranslate2.get_cuda_device_count()`/ctypes libcuda). Failing test → implement →
      pass, following `tests/` patterns. Backend A path unchanged (assert nvidia-smi still used when
      `FLATPAK_ID` unset).
- [ ] Point the CUDA download dir + `LD_LIBRARY_PATH` at `~/.var/app/<id>/data/.../cuda`
      (`cudnn/lib:cublas/lib:cuda_runtime/lib`).
- [ ] Verify: after CUDA download, `device=cuda`, no CPU fallback, transcription fast.
- [ ] Commit.

## Phase 4 — UX parity

Goal: first-run + menus match the AppImage.

- [ ] TDD: `FLATPAK_ID`-gated updater no-op — hide/disable "Check for Updates" (flatpak updates
      externally). Failing test → implement → pass.
- [ ] Onboarding copy: explain the desktop-assigned hotkey (KDE System Settings / GNOME picker).
- [ ] Verify recording-indicator position (fallback-x11), notifications, clipboard/paste (wl-copy),
      Help/About text — all parity.
- [ ] Commit.

## Phase 5 — GNOME cross-check

- [ ] Copy the bundle to the GNOME VM; repeat Phases 2–4 (picker instead of System Settings).
- [ ] Record diffs in `packaging/flatpak/NOTES.md`; fix any GNOME-specific gaps.
- [ ] Commit.

## Phase 6 — Package + distribute

- [ ] `build-flatpak.sh` also emits a single-file `.flatpak` bundle
      (`flatpak build-bundle`) + SHA256.
- [ ] Document install (`flatpak install --user TalkType.flatpak`) in `packaging/flatpak/README.md`.
- [ ] Verify a fresh install from the bundle runs end-to-end on KDE.
- [ ] Commit; open the question of merging `flatpak-manifest` → `main` + a release.

---

## Self-Review

- **Spec coverage:** runtime/GI (P1 step 2,5), Python deps (P1 s3), PortAudio (P1 s4), AppIndicator
  (P1 s5), Backend B (P2), GPU download+detection (P3), updater/onboarding/indicator/clipboard (P4),
  KDE+GNOME (P2–P5), packaging/self-hosted bundle (P6). ✓
- **Placeholder note:** Phases 2–6 are milestone-level by design (integration work whose exact steps
  depend on Phase-1 build discoveries — e.g. the AppIndicator module tags). They are fleshed out to
  bite-sized TDD steps at the start of each phase, not up front, to avoid fabricated specifics.
- **Type consistency:** `FLATPAK_ID` gate, CUDA `LD_LIBRARY_PATH` order, `--device=dri`, app-id used
  consistently and match the spec + spike FINDINGS. ✓

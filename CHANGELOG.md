# Changelog

All notable changes to TalkType are documented here.

## [0.5.15] - 2026-03-22

### New Features
- **Performance Presets** — Choose from Battery Saver, Light, Balanced, Quality, or Most Accurate via the tray menu or GNOME extension
- **Unified CUDA + Model Download** — When selecting a preset that needs both CUDA libraries and a new model, a single download window handles both with clear progress bars and explanatory text
- **Smart Model Selection** — Large-v3 model is no longer grayed out; clicking it explains what's needed (CUDA download for NVIDIA users, or "NVIDIA required" for AMD/Intel) and offers to set it up

### Improvements
- **Onboarding** — Streamlined Setup Complete page with constrained model picker width, shorter labels, and dynamic button text ("Download and Get Started!" vs "Get Started!" based on cache state)
- **Hotkey Test** — Redesigned to be phantom-proof: keys show yellow "Holding..." on press and green "✓ Working!" on release, eliminating false positives from synthetic key events
- **CUDA Crash Loop Prevention** — Performance presets now verify CUDA availability before saving device=cuda, preventing repeated crashes when CUDA libraries aren't installed
- **CPU Fallback** — If CUDA fails at runtime, TalkType automatically falls back to CPU and persists the change to config so it doesn't crash again on restart
- **Preferences Consistency** — Model and preset selection in Preferences now behaves identically to the tray menu (click-to-explain instead of grayed-out)

### Bug Fixes
- Fixed large-v3 model selection showing a blocking confirmation dialog instead of offering CUDA download
- Fixed CUDA download from tray icon using a thread-blocking function that froze the UI
- Fixed double confirmation dialog when downloading CUDA from the tray menu
- Fixed GTK auto-repeat flooding the hotkey test with hundreds of key events when holding a key
- Fixed phantom F8 key events from evdev service termination appearing as false "Working!" results

## [0.5.14] - 2026-03-21

### Improvements
- Bumped version for internal testing

## [0.5.13] - 2026-02-18

### New Features
- **Always-Active Dual Hotkeys** — F8 (hold-to-talk) and F9 (tap-to-toggle) are now both active simultaneously
- Added "Restart Service" menu item to tray and GNOME extension

### Bug Fixes
- Fixed welcome dialog hotkey test false-positive from GNOME's Alt+F8 window-resize keybinding
- Fixed crash after model download (Python 3.10 f-string compatibility)
- Fixed "Setup Complete" screen text alignment

### Performance
- Config file cached — only re-read when changed on disk
- Regex patterns in auto-punctuation engine precompiled at startup

## [0.5.12] - 2026-02-17

### Bug Fixes
- Fixed audio device compatibility for non-standard sample rates

## [0.5.11] - 2026-02-13

### Bug Fixes
- Improved dictation accuracy and hallucination filtering
- Fixed longer paragraphs losing middle sentences during dictation

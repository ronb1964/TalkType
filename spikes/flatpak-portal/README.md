# Flatpak portal-input spike (DISPOSABLE)

Throwaway prototypes proving portal-based typing + global hotkeys for the
future Flatpak. NOT imported by the app or any build. Safe to delete after
FINDINGS.md is written. See docs/superpowers/specs/2026-08-15-flatpak-portal-input-spike-design.md.

Run (from repo root, inside a graphical Wayland session):
  python3 spikes/flatpak-portal/probe_env.py
  python3 spikes/flatpak-portal/hotkey_portal.py
  python3 spikes/flatpak-portal/type_portal.py

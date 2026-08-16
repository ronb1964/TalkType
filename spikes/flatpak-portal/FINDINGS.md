# Flatpak portal-input spike — FINDINGS

**Date:** 2026-08-15/16 · **Host:** Fedora 44, KDE Plasma 6.7, Wayland, libei 1.5.0,
xdg-desktop-portal 1.22.1 · **Spec:** `docs/superpowers/specs/2026-08-15-flatpak-portal-input-spike-design.md`

## Bottom line

**The two capabilities the Flatpak sandbox blocks — typing into other apps and a
global hotkey — are BOTH proven working from Python inside a real Flatpak on KDE.**
The hardest risk in the whole Flatpak plan (can Python drive sandbox-friendly input?)
is retired. Typing uses **libei via ctypes**; the hotkey uses the **GlobalShortcuts
portal**. No GObject-Introspection binding and no helper binary are required. GPU is
deferred per the parent plan. Remaining validation: repeat on GNOME (Task 4).

## Results

| Capability | KDE Plasma (host) | GNOME (VM) |
|---|---|---|
| Portal version | xdg-desktop-portal 1.22.1 | pending (Task 4) |
| libei present in runtime | host libei 1.5.0; org.gnome.Platform//48 ships libei.so | pending |
| Typing method that worked | **ctypes → libei.so.1** (no GI typelib, no helper) | pending |
| Typed test string landed (bare host) | ✅ `hello, world.` into KWrite | n/a |
| Typed test string landed (in Flatpak) | ✅ into focused app; EIS fd survives sandbox | pending |
| Hotkey bind (bare host) | ❌ blocked — "app id required" (see below) | pending |
| Hotkey bind (in Flatpak) | ✅ CreateSession + BindShortcuts succeed | pending |
| Activated on press | ✅ (in Flatpak) | pending |
| Deactivated on release | ✅ (in Flatpak) → hold-to-talk + toggle both viable | pending |
| Where the user assigns the key | KDE System Settings → Keyboard → Shortcuts (no picker dialog) | GNOME uses a picker (expected) |
| Clipboard / paste mode | ✅ wl-copy/wl-paste round-trip OK | pending |

## What we learned (the gotchas that will bite the real Backend B)

1. **libei from Python = ctypes against `libei.so.1`.** Fedora ships libei but *no*
   `Ei` GI typelib, so `from gi.repository import Ei` fails. ctypes works fine.
   - **Set `restype`/`argtypes` on every non-variadic libei function** or 64-bit
     pointers silently truncate to 32-bit → SIGSEGV.
   - **`ei_seat_bind_capabilities` is variadic (sentinel NULL):** pass explicit
     ctypes objects — `c_void_p(seat), c_uint(EI_DEVICE_CAP_KEYBOARD=4), c_void_p(0)`
     — or the seat pointer truncates and crashes. This was the main libei trap.
   - **Event flow:** CONNECT(1) → SEAT_ADDED(3) [bind keyboard cap] → DEVICE_ADDED(5)
     → DEVICE_RESUMED(8) [now ready] → `ei_device_start_emulating` → per char:
     `ei_device_keyboard_key(dev, evdev_keycode, press)` + `ei_device_frame(dev,
     ei_now(ctx))` → `ei_device_stop_emulating`; keep dispatching briefly to flush.
   - Keycodes are evdev/linux codes; the compositor applies the active XKB layout.

2. **RemoteDesktop (typing) needs no app id on the host; GlobalShortcuts (hotkey)
   does.** Testing the hotkey OUTSIDE a sandbox on KDE is effectively blocked:
   `GlobalShortcuts.CreateSession` → "An app id is required", and the host
   `Registry.Register` won't accept an id it has no app-info for (installing the
   `.desktop`, a systemd app-scope, and restarting the portal all failed to satisfy
   KDE). **This is a non-sandbox artifact only** — inside a Flatpak the app id is
   intrinsic (Register is actively refused: "Can't manually register a org.flatpak
   application") and the gate disappears. **Lesson: validate the hotkey inside a
   Flatpak, not on the bare host.**

3. **Inside the sandbox, subscribe to portal signals with `sender=None`** — the
   Activated/Deactivated signals are proxied, so filtering on the bus name misses them.

4. **KDE vs GNOME hotkey UX differs.** KDE registers the portal shortcut with no key
   and the user assigns it in System Settings; GNOME pops a picker. Both deliver the
   same Activated/Deactivated events. The onboarding must explain "your desktop will
   ask you to set the key" and, on KDE, may need to point the user at System Settings.

5. **`org.gnome.Platform//48` is the right runtime base.** It already ships python3,
   PyGObject (`gi`), the Gio typelib, and `libei.so` — so the input layer needs
   nothing extra bundled. The eventual manifest adds faster-whisper/ctranslate2 on top.

6. **A throwaway Flatpak needs no flatpak-builder** — `flatpak build-init` /
   `build-finish` / `build-export` + a `--no-gpg-verify` user remote is enough.
   `finish-args` that worked: `--socket=wayland --socket=fallback-x11 --share=ipc
   --talk-name=org.freedesktop.portal.Desktop`. **No `--device` perms needed** — a
   clean permission set that should pass Flathub review.

## Recommendation for the real Backend B

- **libei access method:** ctypes against `libei.so.1`. Ship on the GNOME runtime
  (has libei); guard all calls with argtypes/restype; wrap the variadic bind call
  with explicit ctypes types. No helper binary, no GI dependency.
- **Typing:** RemoteDesktop portal → SelectDevices(KEYBOARD) → Start → ConnectToEIS
  → libei. Persist the RemoteDesktop session with a `restore_token`/`persist_mode`
  so the user approves the remote-control dialog once, not every launch.
- **Hotkey:** GlobalShortcuts portal; wire `Activated`→start (hold) / toggle and
  `Deactivated`→stop (hold). Subscribe with `sender=None`. Don't call Registry in a
  sandbox. Onboarding: explain the desktop-drawn bind step; on KDE route "change
  hotkey" to System Settings, on GNOME re-invoke the picker.
- **Backend selection:** detect `FLATPAK_ID` at startup → Backend B (portals);
  else Backend A (evdev + ydotool), unchanged. Add, don't replace.
- **Clipboard/paste:** unchanged (`wl-copy`) — works under the Wayland socket.
- **Open risks carried into the manifest sub-project:** (a) confirm all of the above
  on GNOME (Task 4); (b) GPU/NVIDIA add-on is a separate later effort; (c) verify the
  recording-indicator positioning under the sandbox; (d) decide restore_token storage.

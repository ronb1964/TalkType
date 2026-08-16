# Flatpak Portal-Input Spike — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove, with throwaway prototypes on KDE + GNOME, that TalkType can (1) type into other apps via the RemoteDesktop/libei portal path and (2) register a working global hotkey via the GlobalShortcuts portal — then write down which method works and how the real Flatpak input backend should be built.

**Architecture:** Standalone scripts in a disposable `spikes/flatpak-portal/` directory. Portal handshakes use **GDBus via `gi.repository.Gio`** (already available — TalkType is a PyGObject app). Keystroke transport uses **libei** reached from Python by the first method that works: GObject Introspection (`gi.repository.Ei`) → `ctypes` against `libei.so.1` → a small helper binary. Nothing here is wired into `app.py`, the tray, or the build.

**Tech Stack:** Python 3, `gi.repository.Gio`/`GLib` (GDBus + main loop), libei 1.5.0, xdg-desktop-portal (RemoteDesktop + GlobalShortcuts interfaces), KDE Plasma 6.7 (host) + a GNOME VM.

## Global Constraints

- **Throwaway only:** no prototype code may be imported by `app.py`, `tray.py`, `service_launcher.py`, the tray, or any build script. Live in `spikes/flatpak-portal/`.
- **Add-don't-replace:** the existing evdev+ydotool path (Backend A) stays the universal fallback regardless of outcome. This spike does not modify or remove it.
- **Two target desktops:** every capability must be demonstrated on **KDE Plasma (host)** and a **GNOME VM**. KDE-only success is not "done."
- **Verification is observational on a live desktop.** A task's acceptance is a human-witnessed outcome (text appears in an editor; both key signals log), not a headless pytest. Automated tests are used only for pure parsing logic (Task 1).
- **App ID for portal window/handle identification:** `io.github.ronb1964.TalkType`.
- **Test string for typing:** exactly `hello, world.` (letters, comma, space, period — mirrors punctuated dictation output).
- **Plain-language findings:** Ron cannot read code; the Task 6 write-up must explain outcomes in plain language (say "NVIDIA graphics card," not "CUDA," per project tone rules).

---

## File Structure

- `spikes/flatpak-portal/README.md` — what this dir is, how to run each script, "disposable" warning.
- `spikes/flatpak-portal/probe_env.py` — reports portal/libei/typelib availability; has one pure helper worth unit-testing.
- `spikes/flatpak-portal/tests/test_probe_env.py` — unit test for the probe's parsing helper.
- `spikes/flatpak-portal/hotkey_portal.py` — GlobalShortcuts portal prototype (bind + log Activated/Deactivated).
- `spikes/flatpak-portal/type_portal.py` — RemoteDesktop portal handshake → EIS fd → libei → type the test string.
- `spikes/flatpak-portal/_portal_common.py` — shared GDBus request/response helper used by both portal scripts.
- `spikes/flatpak-portal/FINDINGS.md` — the real deliverable (per-desktop results + Backend B recommendation).

---

## Task 1: Spike scaffold + environment probe

Confirms, in a repeatable script, exactly what the portal/libei situation is on a given machine. Run on the host now; rerun on the GNOME VM in Task 4. The probe's version-parsing helper is pure logic and gets a real unit test.

**Files:**
- Create: `spikes/flatpak-portal/README.md`
- Create: `spikes/flatpak-portal/probe_env.py`
- Create: `spikes/flatpak-portal/tests/test_probe_env.py`

**Interfaces:**
- Produces: `probe_env.parse_portal_version(version_str: str) -> tuple[int, int]` — parses an `xdg-desktop-portal` version like `"1.22.1-1.fc44.x86_64"` into `(major, minor)`; used by the probe to check the ≥1.21 libei-portal floor. Later tasks don't import this; it exists so the probe can decide `libei_portal_ok`.

- [ ] **Step 1: Create the disposable-dir README**

`spikes/flatpak-portal/README.md`:

```markdown
# Flatpak portal-input spike (DISPOSABLE)

Throwaway prototypes proving portal-based typing + global hotkeys for the
future Flatpak. NOT imported by the app or any build. Safe to delete after
FINDINGS.md is written. See docs/superpowers/specs/2026-08-15-flatpak-portal-input-spike-design.md.

Run (from repo root, inside a graphical Wayland session):
  python3 spikes/flatpak-portal/probe_env.py
  python3 spikes/flatpak-portal/hotkey_portal.py
  python3 spikes/flatpak-portal/type_portal.py
```

- [ ] **Step 2: Write the failing unit test for the version parser**

`spikes/flatpak-portal/tests/test_probe_env.py`:

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe_env import parse_portal_version

def test_parses_fedora_version():
    assert parse_portal_version("1.22.1-1.fc44.x86_64") == (1, 22)

def test_parses_bare_version():
    assert parse_portal_version("1.21.0") == (1, 21)

def test_unknown_returns_zeroes():
    assert parse_portal_version("not-a-version") == (0, 0)
```

- [ ] **Step 3: Run it to confirm it fails**

Run: `python3 -m pytest spikes/flatpak-portal/tests/test_probe_env.py -v`
Expected: FAIL — `ModuleNotFoundError` / `cannot import name 'parse_portal_version'`.

- [ ] **Step 4: Write `probe_env.py`**

```python
#!/usr/bin/env python3
"""Report portal + libei availability on this machine. Read-only; no injection."""
import ctypes, os, re, shutil, subprocess

def parse_portal_version(version_str: str) -> tuple[int, int]:
    """Parse 'x.y...' out of an rpm/version string. (0, 0) if unrecognised."""
    m = re.match(r"(\d+)\.(\d+)", version_str.strip())
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)

def _portal_version() -> str:
    for cmd in (["rpm", "-q", "--qf", "%{VERSION}", "xdg-desktop-portal"],
                ["dpkg-query", "-W", "-f=${Version}", "xdg-desktop-portal"]):
        if shutil.which(cmd[0]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
                if out.strip():
                    return out.strip()
            except Exception:
                pass
    return "unknown"

def _has_gi_ei() -> bool:
    try:
        import gi
        gi.require_version("Ei", "1.0")
        from gi.repository import Ei  # noqa: F401
        return True
    except Exception:
        return False

def _libei_soname() -> str | None:
    for name in ("libei.so.1", "libei.so"):
        try:
            ctypes.CDLL(name)
            return name
        except OSError:
            continue
    return None

def _portal_iface_present(iface: str) -> bool:
    """Introspect the portal object for an interface name via gdbus."""
    try:
        out = subprocess.run(
            ["gdbus", "introspect", "--session",
             "--dest", "org.freedesktop.portal.Desktop",
             "--object-path", "/org/freedesktop/portal/desktop"],
            capture_output=True, text=True, timeout=10).stdout
        return iface in out
    except Exception:
        return False

def main():
    ver = _portal_version()
    maj, minr = parse_portal_version(ver)
    print("=== TalkType Flatpak portal-input probe ===")
    print(f"session type      : {os.environ.get('XDG_SESSION_TYPE', '<unset>')}")
    print(f"desktop           : {os.environ.get('XDG_CURRENT_DESKTOP', '<unset>')}")
    print(f"wayland display   : {os.environ.get('WAYLAND_DISPLAY', '<unset>')}")
    print(f"xdg-desktop-portal: {ver}  -> ({maj}.{minr}) "
          f"libei-portal floor >=1.21: {'OK' if (maj, minr) >= (1, 21) else 'TOO OLD'}")
    print(f"libei .so         : {_libei_soname() or 'NOT FOUND'}")
    print(f"gi.repository.Ei  : {'available' if _has_gi_ei() else 'NOT available (expect ctypes/helper)'}")
    print(f"RemoteDesktop portal : {'present' if _portal_iface_present('org.freedesktop.portal.RemoteDesktop') else 'MISSING'}")
    print(f"GlobalShortcuts portal: {'present' if _portal_iface_present('org.freedesktop.portal.GlobalShortcuts') else 'MISSING'}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the unit test to confirm it passes**

Run: `python3 -m pytest spikes/flatpak-portal/tests/test_probe_env.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Run the probe on the KDE host and record output**

Run: `python3 spikes/flatpak-portal/probe_env.py`
Expected (host, per earlier manual probe): session `wayland`, portal `1.22.1 -> (1.22) OK`, libei `libei.so.1`, `gi.repository.Ei` NOT available, both portals present. Paste the actual output into a scratch note for Task 6.

- [ ] **Step 7: Commit**

```bash
git add spikes/flatpak-portal/README.md spikes/flatpak-portal/probe_env.py spikes/flatpak-portal/tests/test_probe_env.py
git commit -m "spike: portal-input environment probe"
```

---

## Task 2: Global-hotkey prototype (GlobalShortcuts portal)

The lower-risk half. Proves we can bind a shortcut and receive **both** press and release, so hold-to-talk and toggle are both achievable. Pure GDBus — no libei.

**Files:**
- Create: `spikes/flatpak-portal/_portal_common.py`
- Create: `spikes/flatpak-portal/hotkey_portal.py`

**Interfaces:**
- Produces: `_portal_common.new_request_token() -> str` and `_portal_common.call_portal(bus, iface, method, params, on_response)` — issue a portal request and invoke `on_response(response_code, results_dict)` when the `Response` signal for that request arrives. Consumed by Task 3 as well.

- [ ] **Step 1: Write the shared portal request/response helper**

`spikes/flatpak-portal/_portal_common.py`:

```python
"""Minimal GDBus helper for the xdg-desktop-portal Request/Response pattern."""
import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

BUS_NAME = "org.freedesktop.portal.Desktop"
OBJ_PATH = "/org/freedesktop/portal/desktop"
_counter = 0

def new_request_token() -> str:
    global _counter
    _counter += 1
    return f"talktype_spike_{_counter}"

def session_bus() -> Gio.DBusConnection:
    return Gio.bus_get_sync(Gio.BusType.SESSION, None)

def _sender_prefix(bus) -> str:
    # unique name ":1.234" -> "1_234" per the portal Request path convention
    return bus.get_unique_name().lstrip(":").replace(".", "_")

def call_portal(bus, iface, method, param_builder, on_response):
    """param_builder(handle_token) -> GLib.Variant of the method's IN args
    (it must embed handle_token in the options a{sv}). on_response(code:int,
    results:dict)."""
    token = new_request_token()
    request_path = f"/org/freedesktop/portal/desktop/request/{_sender_prefix(bus)}/{token}"

    def _on_signal(conn, sender, path, iface_, signal, params):
        code, results = params.unpack()
        on_response(code, results)

    bus.signal_subscribe(BUS_NAME, "org.freedesktop.portal.Request", "Response",
                         request_path, None, Gio.DBusSignalFlags.NONE, _on_signal)
    bus.call_sync(BUS_NAME, OBJ_PATH, iface, method, param_builder(token),
                  None, Gio.DBusCallFlags.NONE, -1, None)
```

- [ ] **Step 2: Write `hotkey_portal.py`**

`spikes/flatpak-portal/hotkey_portal.py`:

```python
#!/usr/bin/env python3
"""Bind a global shortcut via the portal and log press/release. Ctrl+C to quit."""
import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib
import _portal_common as pc

IFACE = "org.freedesktop.portal.GlobalShortcuts"

def main():
    bus = pc.session_bus()
    loop = GLib.MainLoop()
    state = {"session": None}

    def create_session():
        def builder(token):
            opts = {"handle_token": GLib.Variant("s", token),
                    "session_handle_token": GLib.Variant("s", token + "_sess")}
            return GLib.Variant("(a{sv})", (opts,))
        pc.call_portal(bus, IFACE, "CreateSession", builder, on_session)

    def on_session(code, results):
        if code != 0:
            print(f"CreateSession failed: {code}"); loop.quit(); return
        state["session"] = results["session_handle"]
        print(f"session: {state['session']}")
        bind()

    def bind():
        # one shortcut "dictate", suggest F8; desktop draws its own dialog
        shortcuts = GLib.Variant("a(sa{sv})", [
            ("dictate", {"description": GLib.Variant("s", "TalkType: hold to dictate"),
                         "preferred_trigger": GLib.Variant("s", "F8")})])
        def builder(token):
            opts = {"handle_token": GLib.Variant("s", token)}
            return GLib.Variant("(oa(sa{sv})sa{sv})",
                                (state["session"], shortcuts, "", opts))
        pc.call_portal(bus, IFACE, "BindShortcuts", builder, on_bound)

    def on_bound(code, results):
        if code != 0:
            print(f"BindShortcuts failed/cancelled: {code}"); loop.quit(); return
        print("bound. Now HOLD then RELEASE your chosen key. Ctrl+C to quit.")

    def on_activated(conn, s, p, i, sig, params):
        print(f"  >>> Activated   {params.unpack()[1]}")
    def on_deactivated(conn, s, p, i, sig, params):
        print(f"  >>> Deactivated {params.unpack()[1]}")

    bus.signal_subscribe(pc.BUS_NAME, IFACE, "Activated", None, None,
                         Gio.DBusSignalFlags.NONE, on_activated)
    bus.signal_subscribe(pc.BUS_NAME, IFACE, "Deactivated", None, None,
                         Gio.DBusSignalFlags.NONE, on_deactivated)
    create_session()
    loop.run()

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run on the KDE host (interactive — Ron approves the dialog)**

Run: `python3 spikes/flatpak-portal/hotkey_portal.py`
Expected: KDE shows its own shortcut-bind dialog; after Ron sets/accepts a key, the script prints `bound.` Then holding the key prints `>>> Activated` and releasing prints `>>> Deactivated`.

- [ ] **Step 4: Acceptance check (both signals)**

PASS only if a single hold produces exactly one `Activated` on press and one `Deactivated` on release. Record whether KDE pre-filled F8 or required manual entry. If `Deactivated` never fires, note it — that would force toggle-only mode and is a key finding.

- [ ] **Step 5: Commit**

```bash
git add spikes/flatpak-portal/_portal_common.py spikes/flatpak-portal/hotkey_portal.py
git commit -m "spike: GlobalShortcuts portal hotkey prototype (press+release)"
```

---

## Task 3: Typing prototype (RemoteDesktop portal → EIS → libei)

The high-risk half and the spike's whole reason to exist. Handshake is concrete GDBus; the libei transport is the exploration frontier. **Stop as soon as `hello, world.` lands in a real editor** — do not gold-plate.

**Files:**
- Create: `spikes/flatpak-portal/type_portal.py`

**Interfaces:**
- Consumes: `_portal_common.call_portal`, `_portal_common.session_bus`.
- Produces: nothing for later code (throwaway). Produces a **finding**: which libei access method worked.

- [ ] **Step 1: Write the RemoteDesktop handshake up to the EIS fd**

`spikes/flatpak-portal/type_portal.py` (handshake portion — concrete, should work as-is):

```python
#!/usr/bin/env python3
"""RemoteDesktop portal -> ConnectToEIS -> libei -> type 'hello, world.'."""
import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib
import _portal_common as pc

IFACE = "org.freedesktop.portal.RemoteDesktop"
KEYBOARD = 1  # DeviceType bitmask: KEYBOARD=1, POINTER=2, TOUCHSCREEN=4

def main():
    bus = pc.session_bus()
    loop = GLib.MainLoop()
    st = {"session": None, "eis_fd": None}

    def create_session():
        def b(token):
            opts = {"handle_token": GLib.Variant("s", token),
                    "session_handle_token": GLib.Variant("s", token + "_sess")}
            return GLib.Variant("(a{sv})", (opts,))
        pc.call_portal(bus, IFACE, "CreateSession", b, on_session)

    def on_session(code, results):
        if code: print(f"CreateSession failed {code}"); loop.quit(); return
        st["session"] = results["session_handle"]; select_devices()

    def select_devices():
        def b(token):
            opts = {"handle_token": GLib.Variant("s", token),
                    "types": GLib.Variant("u", KEYBOARD)}
            return GLib.Variant("(oa{sv})", (st["session"], opts))
        pc.call_portal(bus, IFACE, "SelectDevices", b, lambda c, r: start() if not c else fail(c))

    def start():
        def b(token):
            opts = {"handle_token": GLib.Variant("s", token)}
            return GLib.Variant("(osa{sv})", (st["session"], "", opts))
        pc.call_portal(bus, IFACE, "Start", b, lambda c, r: connect_eis() if not c else fail(c))

    def connect_eis():
        # ConnectToEIS returns a UnixFD (h). Use call_with_unix_fd_list_sync.
        opts = GLib.Variant("(oa{sv})", (st["session"], {}))
        ret, fd_list = bus.call_with_unix_fd_list_sync(
            pc.BUS_NAME, pc.OBJ_PATH, IFACE, "ConnectToEIS", opts,
            GLib.VariantType("(h)"), Gio.DBusCallFlags.NONE, -1, None, None)
        fd_index = ret.unpack()[0]
        st["eis_fd"] = fd_list.get(fd_index)
        print(f"EIS fd = {st['eis_fd']}")
        type_via_libei(st["eis_fd"])
        loop.quit()

    def fail(code): print(f"portal step failed {code}"); loop.quit()
    create_session(); loop.run()

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add the libei transport — attempt GObject Introspection first**

Append a `type_via_libei(fd)` that tries GI, else falls through to ctypes (Step 3). The probe says GI is absent on the host, so this branch is mostly for the GNOME VM:

```python
def type_via_libei(fd):
    if _try_gi(fd): return
    if _try_ctypes(fd): return
    print("!! No Python libei path worked — fall back to a helper binary (Step 4).")

def _try_gi(fd) -> bool:
    try:
        import gi; gi.require_version("Ei", "1.0")
        from gi.repository import Ei
    except Exception:
        print("[gi] Ei typelib unavailable"); return False
    # If present, build a sender context, ei_setup_backend_fd(fd), create a
    # keyboard device, and emit key press/release for 'hello, world.'.
    # Fill in against the installed Ei API; return True on success.
    print("[gi] Ei present — implement against this API"); return False
```

- [ ] **Step 3: Add the ctypes libei transport (the expected host path)**

Concrete ctypes skeleton against the real libei C API (`ei_new_sender`, `ei_setup_backend_fd`, dispatch loop, `ei_seat`/`ei_device` keyboard, `ei_device_keyboard_key`). This is the frontier — iterate until keystrokes land:

```python
import ctypes as C

def _try_ctypes(fd) -> bool:
    try:
        ei = C.CDLL("libei.so.1")
    except OSError:
        print("[ctypes] libei.so.1 not loadable"); return False
    # Real API (libei 1.5): ei* ei_new_sender(void *user_data);
    #   int ei_setup_backend_fd(struct ei *, int fd);
    #   then run the ei event loop: ei_dispatch(), poll ei_get_fd(),
    #   handle EI_EVENT_SEAT_ADDED -> ei_seat_bind_capabilities(seat, KEYBOARD),
    #   EI_EVENT_DEVICE_ADDED (keyboard) -> ei_device_start_emulating(dev, seq),
    #   ei_device_keyboard_key(dev, keycode, true/false) for each char,
    #   ei_device_frame(dev, now). Keycodes are XKB/evdev (e.g. KEY_H=35).
    #   Declare argtypes/restypes for each call before use.
    # Build the minimal sequence to emit 'hello, world.' then flush.
    print("[ctypes] libei loaded — implement emit sequence, return True on success")
    return False
```

Iterate here (declare `argtypes`/`restype`, drive the ei event loop, map each character of `hello, world.` to its evdev keycode with shift for punctuation) until the string types into a focused editor.

- [ ] **Step 4: Fallback — helper binary (only if Steps 2–3 both fail)**

If Python cannot drive libei acceptably, wrap a tiny known-good libei client and shell out to it. Candidates: the Rust `reis` crate's example sender, or a ~40-line C program using `libei` that reads text on argv and emits it. Document exactly which, and that the eventual Flatpak must bundle it. Do not build this unless Steps 2–3 are exhausted.

- [ ] **Step 5: Acceptance check on the KDE host (interactive)**

Open a text editor (Kate/gedit), focus it, run `python3 spikes/flatpak-portal/type_portal.py`, approve the RemoteDesktop dialog. PASS when `hello, world.` appears in the editor. Record which of GI / ctypes / helper worked, and the libei version.

- [ ] **Step 6: Commit**

```bash
git add spikes/flatpak-portal/type_portal.py
git commit -m "spike: RemoteDesktop/libei typing prototype (types via portal)"
```

---

## Task 4: Cross-desktop validation on a GNOME VM

Proves KDE success wasn't compositor-specific. GNOME has historically differed (per 0.7.0 history), so this is mandatory, not optional.

**Files:** none (runs the existing prototypes on another machine).

- [ ] **Step 1: Stand up a GNOME VM**

Restore or create an Ubuntu (GNOME, Wayland) VM in virt-manager. If networking misbehaves, apply the libvirt `iptables` backend fix recorded in the Obsidian packaging note. Copy the `spikes/flatpak-portal/` dir into the VM (e.g. `python3 -m http.server` over `virbr0`, as in prior sessions).

- [ ] **Step 2: Run the probe in the VM**

Run: `python3 spikes/flatpak-portal/probe_env.py`
Record the output. Note especially whether `gi.repository.Ei` is available on GNOME/Ubuntu (may differ from Fedora) and the portal version.

- [ ] **Step 3: Run the hotkey prototype in the VM**

Run: `python3 spikes/flatpak-portal/hotkey_portal.py`
Acceptance: GNOME's bind dialog appears; press logs `Activated`, release logs `Deactivated`. Record whether GNOME pre-fills the suggested key and whether release fires (GNOME parity with KDE is the thing under test).

- [ ] **Step 4: Run the typing prototype in the VM**

Run: `python3 spikes/flatpak-portal/type_portal.py` into a focused gedit/Text Editor.
Acceptance: `hello, world.` appears. Record which libei method worked on GNOME (it may be GI where the host needed ctypes — a real finding).

- [ ] **Step 5: No commit** (no code changed; results go into Task 6).

---

## Task 5: Clipboard/paste quick confirm (5 minutes, not a build)

Paste mode is low-risk (own-set clipboard works under Flatpak) but cheap to confirm now so the later manifest work has no surprises.

**Files:** none.

- [ ] **Step 1: Confirm own-set clipboard works in a normal session**

On the KDE host, run `wl-copy "talktype clipboard check"` then paste (Ctrl+V) into an editor. Confirm it appears. This mirrors what paste mode does. Record one line in FINDINGS.md: paste-mode clipboard path — confirmed / caveat. Deeper Flatpak clipboard-portal testing is deferred to the manifest sub-project.

---

## Task 6: Findings write-up (the real deliverable)

Turns the disposable prototypes into durable knowledge that unblocks the next sub-project.

**Files:**
- Create: `spikes/flatpak-portal/FINDINGS.md`
- Update (Obsidian): a new note linked from the packaging plan.

- [ ] **Step 1: Write `FINDINGS.md`**

Include a per-desktop results table and a recommendation. Structure:

```markdown
# Flatpak portal-input spike — FINDINGS

## Results
| Capability | KDE Plasma (host) | GNOME (VM) |
|---|---|---|
| Portal version | 1.22.1 | <fill> |
| Typing method that worked | <GI/ctypes/helper> | <...> |
| Typed test string landed | <yes/no> | <...> |
| Hotkey bind dialog | <pre-fill? manual?> | <...> |
| Activated on press | <yes/no> | <...> |
| Deactivated on release | <yes/no> | <...> |
| Rebind from app or system settings? | <...> | <...> |

## Recommendation for the real Backend B
- libei access method to build on: <...>
- Helper binary needed? <yes/no; which>
- Hotkey: hold-to-talk viable? toggle viable? <...>
- Onboarding implication (bind dialog is desktop-drawn): <...>
- Sandbox-detection switch (FLATPAK_ID) selecting Backend A vs B: <one line>
- Open risks carried into the manifest sub-project: <...>
```

- [ ] **Step 2: Fill the table from Tasks 1–5 records** (plain language; no jargon per project tone rules).

- [ ] **Step 3: Write the Obsidian note**

Use `mcp__obsidian__write_note` to create `TalkType/2026-08-15 - Flatpak portal spike results.md`, summarising the findings + recommendation, and link it from *"2026-08-15 - Packaging expansion plan (deb, rpm, Flatpak)"* (add a `[[...]]` under Phase 3).

- [ ] **Step 4: Commit**

```bash
git add spikes/flatpak-portal/FINDINGS.md
git commit -m "spike: portal-input findings + Backend B recommendation"
```

- [ ] **Step 5: Decide the disposition of the spike branch**

Present to Ron: the spike proved/disproved the portal path; recommend whether to (a) keep `spikes/flatpak-portal/` on a merge to main as reference, or (b) delete the prototypes and keep only FINDINGS.md + the Obsidian note. Do not merge or delete without Ron's decision.

---

## Self-Review

**Spec coverage:**
- Spec Goal 1 (typing) → Task 3 (+ Task 4 GNOME). ✓
- Spec Goal 2 (hotkey press+release) → Task 2 (+ Task 4 GNOME). ✓
- Spec Goal 3 (findings + Backend B recommendation) → Task 6. ✓
- Spec Part A three-method ladder (GI → ctypes → helper) → Task 3 Steps 2/3/4. ✓
- Spec Part B (bind dialog desktop-drawn; rebind behaviour) → Task 2 Step 4, Task 6 table. ✓
- Spec "both desktops" constraint → Task 4. ✓
- Spec clipboard 5-min confirm → Task 5. ✓
- Spec "out of scope" (manifest, GPU, app.py refactor, onboarding UI) → not present as tasks. ✓ (correctly excluded)
- Spec "throwaway / not wired into app" → Global Constraints + Task 6 Step 5 disposition. ✓

**Placeholder scan:** The libei transport in Task 3 Steps 2–4 is intentionally an *iteration frontier* with a concrete starting implementation and named fallbacks — this is the nature of a spike, not a "TODO: implement." All portal-handshake code (Tasks 1–2, Task 3 Step 1) is concrete and runnable. No forbidden placeholders elsewhere.

**Type consistency:** `_portal_common.call_portal(bus, iface, method, param_builder, on_response)` and `session_bus()` are defined in Task 2 Step 1 and consumed identically in Task 3 Step 1. `parse_portal_version` signature matches between Task 1 interface block, test, and implementation. Portal `DeviceType` KEYBOARD=1 used consistently. ✓

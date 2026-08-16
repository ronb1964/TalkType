# Flatpak Backend B Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a swappable input/output backend seam so TalkType dictates via desktop portals inside a Flatpak (`FLATPAK_ID` set) and via evdev+ydotool everywhere else — without changing the non-Flatpak path.

**Architecture:** Two thin interfaces — an OutputBackend (`type_text(text)->bool`) and an InputBackend (drives the existing `_cmd_start_recording`/`_cmd_stop_recording` events) — selected once at startup by `FLATPAK_ID`. Backend A wraps today's evdev+ydotool code unchanged; Backend B is the portal code proven in the spike (`spikes/flatpak-portal/`), productionized. The recording/transcription core in `app.py` is untouched.

**Tech Stack:** Python 3, `gi.repository.Gio`/`GLib` (GDBus + main loop), libei 1.5 via `ctypes`, xdg-desktop-portal (RemoteDesktop + GlobalShortcuts), evdev, ydotool.

## Global Constraints

- **Add, don't replace:** the evdev+ydotool path (Backend A) stays byte-for-byte behaviorally unchanged. A Backend B bug must be incapable of affecting non-Flatpak installs.
- **Selection:** `os.environ.get("FLATPAK_ID")` truthy → Backend B; else Backend A. One decision point.
- **Proven mechanisms only:** typing = RemoteDesktop → ConnectToEIS → libei via ctypes; hotkey = GlobalShortcuts portal, ONE `dictate` shortcut (its `Activated`/`Deactivated` cover hold AND toggle). Source of truth: `spikes/flatpak-portal/{type_portal.py,hotkey_portal.py,_portal_common.py}`.
- **libei ctypes rules:** set `restype`/`argtypes` on every non-variadic call; `ei_seat_bind_capabilities` is variadic — pass explicit ctypes objects (`c_void_p(seat), c_uint(EI_DEVICE_CAP_KEYBOARD=4), c_void_p(0)`).
- **In-sandbox portal signals:** subscribe with `sender=None`; do NOT call `Registry.Register` when `FLATPAK_ID` is set.
- **Runtime:** `org.gnome.Platform//48` (ships python+gi+Gio typelib+libei). No extra bundling for input.
- **Tests need system PyGObject:** run pytest as `PYTHONPATH=/usr/lib64/python3.14/site-packages:/usr/lib/python3.14/site-packages:src .venv/bin/python -m pytest`.
- **Out of scope (later sub-projects):** production manifest, onboarding UX, GPU add-on, Flathub. Clipboard/paste unchanged.

---

## File Structure

- `src/talktype/output_backends.py` — CREATE. `OutputBackend` base, `YdotoolOutputBackend`, `LibeiOutputBackend`, `get_output_backend()`.
- `src/talktype/input_backends.py` — CREATE. `InputBackend` base, `EvdevInputBackend`, `PortalInputBackend`, `get_input_backend()`.
- `src/talktype/portal_common.py` — CREATE (port of `spikes/flatpak-portal/_portal_common.py`). GDBus Request/Response helper.
- `src/talktype/libei_ctypes.py` — CREATE (port of the libei parts of `spikes/flatpak-portal/type_portal.py`). ctypes wrapper + keycode map.
- `src/talktype/app.py` — MODIFY. Route the post-transcription typing through the output backend; run the evdev loop OR the portal loop by backend; extract the shared consumer body.
- `tests/test_backend_select.py`, `tests/test_output_backends.py`, `tests/test_libei_ctypes.py`, `tests/test_portal_common.py` — CREATE.
- `spikes/flatpak-portal/build_real_flatpak.sh` — CREATE. Wrap the real app in the throwaway Flatpak for integration testing.

---

## Task 1: Backend selection

Establishes the `FLATPAK_ID` switch and the interface base classes, with Backend B as stubs so selection is testable before the portal code exists.

**Files:**
- Create: `src/talktype/output_backends.py`, `src/talktype/input_backends.py`
- Test: `tests/test_backend_select.py`

**Interfaces:**
- Produces: `output_backends.OutputBackend` (base, `.type_text(text: str) -> bool`); `output_backends.get_output_backend(flatpak_id=None) -> OutputBackend`. `input_backends.InputBackend` (base, `.start()`, `.stop()`); `input_backends.get_input_backend(flatpak_id=None) -> InputBackend`. `flatpak_id=None` means read `os.environ`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backend_select.py
from talktype.output_backends import get_output_backend, YdotoolOutputBackend, LibeiOutputBackend
from talktype.input_backends import get_input_backend, EvdevInputBackend, PortalInputBackend

def test_output_backend_is_ydotool_without_flatpak():
    assert isinstance(get_output_backend(flatpak_id=""), YdotoolOutputBackend)

def test_output_backend_is_libei_in_flatpak():
    assert isinstance(get_output_backend(flatpak_id="io.github.ronb1964.TalkType"), LibeiOutputBackend)

def test_input_backend_is_evdev_without_flatpak():
    assert isinstance(get_input_backend(flatpak_id=""), EvdevInputBackend)

def test_input_backend_is_portal_in_flatpak():
    assert isinstance(get_input_backend(flatpak_id="io.github.ronb1964.TalkType"), PortalInputBackend)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/usr/lib64/python3.14/site-packages:/usr/lib/python3.14/site-packages:src .venv/bin/python -m pytest tests/test_backend_select.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'talktype.output_backends'`.

- [ ] **Step 3: Write the minimal implementation**

`src/talktype/output_backends.py`:
```python
"""Text-injection backends. Backend A = ydotool; Backend B = libei (Flatpak)."""
import os


class OutputBackend:
    def type_text(self, text: str) -> bool:
        raise NotImplementedError


class YdotoolOutputBackend(OutputBackend):
    def type_text(self, text: str) -> bool:
        from . import app
        return app._type_text(text)


class LibeiOutputBackend(OutputBackend):
    def type_text(self, text: str) -> bool:
        raise NotImplementedError("implemented in Task 5")


def get_output_backend(flatpak_id=None) -> OutputBackend:
    if flatpak_id is None:
        flatpak_id = os.environ.get("FLATPAK_ID", "")
    return LibeiOutputBackend() if flatpak_id else YdotoolOutputBackend()
```

`src/talktype/input_backends.py`:
```python
"""Hotkey/input backends. Backend A = evdev; Backend B = GlobalShortcuts (Flatpak).
Both drive the same app._cmd_start_recording / app._cmd_stop_recording events."""
import os


class InputBackend:
    def start(self):
        raise NotImplementedError

    def stop(self):
        pass


class EvdevInputBackend(InputBackend):
    def __init__(self, cfg, input_device_idx):
        self.cfg = cfg
        self.input_device_idx = input_device_idx

    def start(self):
        raise NotImplementedError("implemented in Task 6")


class PortalInputBackend(InputBackend):
    def __init__(self, cfg):
        self.cfg = cfg

    def start(self):
        raise NotImplementedError("implemented in Task 7")


def get_input_backend(flatpak_id=None, cfg=None, input_device_idx=None) -> InputBackend:
    if flatpak_id is None:
        flatpak_id = os.environ.get("FLATPAK_ID", "")
    if flatpak_id:
        return PortalInputBackend(cfg)
    return EvdevInputBackend(cfg, input_device_idx)
```

- [ ] **Step 4: Run test to verify it passes**

Run the same pytest command. Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/talktype/output_backends.py src/talktype/input_backends.py tests/test_backend_select.py
git commit -m "flatpak(backend-b): add input/output backend interfaces + FLATPAK_ID selection"
```

---

## Task 2: Route typing through the output backend (Backend A output)

Makes the post-transcription typing go through `get_output_backend()` instead of calling `_type_text` directly, so Backend B can later swap in. `YdotoolOutputBackend` already delegates to `_type_text`, so behavior is identical when not in a Flatpak.

**Files:**
- Modify: `src/talktype/app.py` (the 4 post-transcription `_type_text(...)` call sites near lines 1881, 1885, 1923, 1947) + a module-level cached backend.
- Test: `tests/test_output_backends.py`

**Interfaces:**
- Consumes: `output_backends.get_output_backend`, `output_backends.YdotoolOutputBackend`.
- Produces: `app._output_backend()` — returns the process-wide cached `OutputBackend`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_output_backends.py
from talktype.output_backends import YdotoolOutputBackend

def test_ydotool_backend_delegates_to_type_text(monkeypatch):
    from talktype import app
    calls = []
    monkeypatch.setattr(app, "_type_text", lambda t: calls.append(t) or True)
    assert YdotoolOutputBackend().type_text("hello") is True
    assert calls == ["hello"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `... -m pytest tests/test_output_backends.py -v`
Expected: PASS already for this test (Ydotool delegates). If it errors on import, fix the import; this test guards the delegation contract Task 5 must preserve.

- [ ] **Step 3: Add the cached accessor + reroute calls in app.py**

Add near the other module-level helpers in `app.py`:
```python
_OUTPUT_BACKEND = None

def _output_backend():
    """Process-wide OutputBackend, chosen once by FLATPAK_ID."""
    global _OUTPUT_BACKEND
    if _OUTPUT_BACKEND is None:
        from .output_backends import get_output_backend
        _OUTPUT_BACKEND = get_output_backend()
    return _OUTPUT_BACKEND
```
Then replace each `inject_ok = _type_text(text)` / `if _type_text(remainder):` call in `stop_recording`'s transcription path (near lines 1881, 1885, 1923, 1947) with `_output_backend().type_text(...)`. Leave `_type_text`/`_type_text_raw` defined (Ydotool backend calls them).

- [ ] **Step 4: Run the full suite**

Run: `... -m pytest -q`
Expected: all pass (Backend A path unchanged — `_output_backend()` returns Ydotool which calls `_type_text`).

- [ ] **Step 5: Commit**

```bash
git add src/talktype/app.py tests/test_output_backends.py
git commit -m "flatpak(backend-b): route post-transcription typing through the output backend"
```

---

## Task 3: libei ctypes wrapper

Ports the proven libei code from `spikes/flatpak-portal/type_portal.py` into a reusable module. Pure-logic parts (keycode map, signature setup) are unit-tested; injection is integration-tested in Task 9.

**Files:**
- Create: `src/talktype/libei_ctypes.py`
- Test: `tests/test_libei_ctypes.py`

**Interfaces:**
- Produces: `libei_ctypes.CHAR_TO_KEYCODE: dict[str,int]`; `libei_ctypes.load_libei() -> ctypes.CDLL` (with restype/argtypes set); `libei_ctypes.EI_EVENT_SEAT_ADDED=3`, `EI_EVENT_DEVICE_RESUMED=8`, `EI_DEVICE_CAP_KEYBOARD=4`; `libei_ctypes.LibeiSession(fd)` with `.pump_until_ready(timeout=10.0) -> bool` and `.type_string(text) -> bool`. Consumed by Task 5.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_libei_ctypes.py
from talktype import libei_ctypes as L

def test_keycode_map_covers_punctuated_output():
    for ch in "hello, world.":
        assert ch in L.CHAR_TO_KEYCODE, f"missing keycode for {ch!r}"
    assert L.CHAR_TO_KEYCODE["h"] == 35 and L.CHAR_TO_KEYCODE[","] == 51

def test_enum_constants():
    assert (L.EI_EVENT_SEAT_ADDED, L.EI_EVENT_DEVICE_RESUMED, L.EI_DEVICE_CAP_KEYBOARD) == (3, 8, 4)

def test_load_libei_sets_signatures_or_skips():
    import ctypes
    try:
        ei = L.load_libei()
    except OSError:
        import pytest; pytest.skip("libei.so.1 not present on this host")
    assert ei.ei_new_sender.restype == ctypes.c_void_p
```

- [ ] **Step 2: Run to verify it fails**

Run: `... -m pytest tests/test_libei_ctypes.py -v` → FAIL (`No module named 'talktype.libei_ctypes'`).

- [ ] **Step 3: Implement by porting the libei code**

Create `src/talktype/libei_ctypes.py`. Move the libei portions of `spikes/flatpak-portal/type_portal.py` verbatim and refactor into: module constants (`EI_EVENT_*`, `EI_DEVICE_CAP_KEYBOARD`, `CHAR_TO_KEYCODE` = the existing `KEY` dict but extended below); `load_libei()` = the existing `_load_libei()`; and a `LibeiSession` class wrapping `ei_new_sender`/`ei_setup_backend_fd`/the dispatch loop (`pump_until_ready`) and the emit loop (`type_string`, from `_emit_string` — remember `ei_now(ctx)` not `ei_now(ei)`). **Extend `CHAR_TO_KEYCODE`** beyond the spike's test string to the full set needed for real dictation: letters (with a Shift path for uppercase), digits, space, and common punctuation `.,?!'";:-()` — map each to its evdev keycode, marking which require Shift. Keep the variadic `ei_seat_bind_capabilities` call using explicit ctypes objects.

- [ ] **Step 4: Run to verify it passes**

Run: `... -m pytest tests/test_libei_ctypes.py -v` → PASS (load test skips if libei absent; present on host).

- [ ] **Step 5: Commit**

```bash
git add src/talktype/libei_ctypes.py tests/test_libei_ctypes.py
git commit -m "flatpak(backend-b): libei ctypes wrapper (LibeiSession + full keycode map)"
```

---

## Task 4: portal_common (GDBus helper)

Ports `spikes/flatpak-portal/_portal_common.py` into the package for both backends.

**Files:**
- Create: `src/talktype/portal_common.py`
- Test: `tests/test_portal_common.py`

**Interfaces:**
- Produces: `portal_common.session_bus()`, `portal_common.new_request_token() -> str`, `portal_common.call_portal(bus, iface, method, param_builder, on_response)`, `portal_common.register_app_id(bus, app_id=APP_ID)`, `portal_common.BUS_NAME`, `portal_common.OBJ_PATH`, `portal_common.APP_ID="io.github.ronb1964.TalkType"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_portal_common.py
from talktype import portal_common as pc

def test_request_tokens_are_unique():
    a, b = pc.new_request_token(), pc.new_request_token()
    assert a != b and a.startswith("talktype")

def test_constants():
    assert pc.BUS_NAME == "org.freedesktop.portal.Desktop"
    assert pc.APP_ID == "io.github.ronb1964.TalkType"
```

- [ ] **Step 2: Run to verify it fails**

Run: `... -m pytest tests/test_portal_common.py -v` → FAIL (module missing).

- [ ] **Step 3: Port the file**

Copy `spikes/flatpak-portal/_portal_common.py` to `src/talktype/portal_common.py` verbatim (it already has `register_app_id`, `call_portal`, `session_bus`, `new_request_token`, `APP_ID`). Change the token prefix from `talktype_spike_` to `talktype_`.

- [ ] **Step 4: Run to verify it passes**

Run: `... -m pytest tests/test_portal_common.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/talktype/portal_common.py tests/test_portal_common.py
git commit -m "flatpak(backend-b): port portal_common GDBus helper into the package"
```

---

## Task 5: LibeiOutputBackend (Backend B typing)

Implements portal typing behind the `OutputBackend.type_text()` contract, establishing a persistent RemoteDesktop/EIS session with a restore token. Verified in Task 9 (needs a sandbox); this task delivers the code + the non-portal guards.

**Files:**
- Modify: `src/talktype/output_backends.py`
- Test: `tests/test_output_backends.py` (add a guard test)

**Interfaces:**
- Consumes: `portal_common`, `libei_ctypes.LibeiSession`.
- Produces: `LibeiOutputBackend.type_text(text) -> bool` (real); `LibeiOutputBackend.ensure_session() -> bool`.

- [ ] **Step 1: Write the failing/guard test**

```python
def test_libei_backend_reports_failure_when_no_session(monkeypatch):
    from talktype.output_backends import LibeiOutputBackend
    b = LibeiOutputBackend()
    monkeypatch.setattr(b, "ensure_session", lambda: False)
    assert b.type_text("hi") is False   # never raises; returns False so caller can notify
```

- [ ] **Step 2: Run to verify it fails**

Run: `... -m pytest tests/test_output_backends.py -v` → FAIL (`ensure_session` not defined / NotImplementedError).

- [ ] **Step 3: Implement LibeiOutputBackend**

Port the RemoteDesktop handshake from `spikes/flatpak-portal/type_portal.py` (`create_session`→`select_devices`→`start`→`connect_eis`) into `ensure_session()`: run it once, cache the EIS fd + a `LibeiSession`, request `persist_mode=2` in the `Start` options and persist the returned `restore_token` to `get_data_dir()/remote_desktop_token` (read it back on next `ensure_session` and pass it into `SelectDevices` options to skip the approval dialog). `type_text(text)` → `ensure_session()`; on success `LibeiSession.type_string(text)` and return its bool; on failure return `False` (never raise). Use `portal_common.call_portal` with a GLib loop for the async Response signals (mirror the spike's `type_portal.main()` control flow, but keep the session/context alive instead of quitting).

- [ ] **Step 4: Run the suite**

Run: `... -m pytest -q` → all pass (the guard test + unchanged Backend A).

- [ ] **Step 5: Commit**

```bash
git add src/talktype/output_backends.py tests/test_output_backends.py
git commit -m "flatpak(backend-b): LibeiOutputBackend — portal typing with a persistent EIS session"
```

---

## Task 6: EvdevInputBackend + extract the shared consumer loop

Wraps today's evdev loop as Backend A, and extracts the backend-agnostic body (consume `_cmd_*` events, auto-timeout, config reload) so Backend B can reuse it without duplicating logic. `_loop_evdev` keeps doing exactly what it does today; it just calls the extracted helper for the shared parts.

**Files:**
- Modify: `src/talktype/app.py` (`_loop_evdev` near 2182; entry at 2679), `src/talktype/input_backends.py`
- Test: existing suite (regression) + `tests/test_backend_select.py` (extend)

**Interfaces:**
- Produces: `app._service_tick(cfg, input_device_idx, state) -> None` — runs one iteration of the shared consumer body (checks `_cmd_start_recording`/`_cmd_stop_recording`, auto-timeout, config-reload) and starts/stops recording accordingly. `EvdevInputBackend.start()` runs the current evdev loop; `PortalInputBackend` (Task 7) will also call `_service_tick`.

- [ ] **Step 1: Write the regression guard test**

```python
def test_evdev_backend_start_is_callable():
    from talktype.input_backends import EvdevInputBackend
    b = EvdevInputBackend(cfg=None, input_device_idx=0)
    assert callable(b.start)
```

- [ ] **Step 2: Run to verify current state**

Run: `... -m pytest -q` → all pass (baseline before refactor).

- [ ] **Step 3: Extract `_service_tick` and wrap in EvdevInputBackend**

In `app.py`, factor the backend-agnostic parts of `_loop_evdev`'s body — the `_cmd_start_recording.is_set()`/`_cmd_stop_recording.is_set()` handling (lines ~2267-2278), the auto-timeout check, and the config-reload check — into `_service_tick(cfg, input_device_idx, state)`. `_loop_evdev` keeps its evdev device reading and calls `_service_tick(...)` each iteration for the shared work (behavior identical). Then `EvdevInputBackend.start()` = `app._loop_evdev(self.cfg, self.input_device_idx)`.

- [ ] **Step 4: Run the full suite + a manual host dictation**

Run: `... -m pytest -q` → all pass. Then run the dev app and confirm hold-to-talk dictation still types (Backend A unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/talktype/app.py src/talktype/input_backends.py tests/test_backend_select.py
git commit -m "flatpak(backend-b): EvdevInputBackend wraps the evdev loop; extract shared _service_tick"
```

---

## Task 7: PortalInputBackend (Backend B hotkey)

Implements the GlobalShortcuts hotkey behind `InputBackend`, translating portal signals into the `_cmd_*` events and running the shared `_service_tick`. Verified in Task 9.

**Files:**
- Modify: `src/talktype/input_backends.py`
- Test: `tests/test_backend_select.py` (extend with a signal-mapping unit test)

**Interfaces:**
- Consumes: `portal_common`, `app._cmd_start_recording`, `app._cmd_stop_recording`, `app._service_tick`, `cfg.mode`.
- Produces: `PortalInputBackend.start()` (blocks, runs the GLib loop + a `_service_tick` timer); `PortalInputBackend._on_activated()/_on_deactivated()` set the `_cmd_*` events per `cfg.mode`.

- [ ] **Step 1: Write the signal-mapping unit test**

```python
def test_portal_hold_mode_maps_press_and_release(monkeypatch):
    from talktype import app
    from talktype.input_backends import PortalInputBackend
    class Cfg: mode = "hold"
    b = PortalInputBackend(Cfg())
    app._cmd_start_recording.clear(); app._cmd_stop_recording.clear()
    b._on_activated(None, None, None, None, None, _fake_params("dictate"))
    assert app._cmd_start_recording.is_set()
    b._on_deactivated(None, None, None, None, None, _fake_params("dictate"))
    assert app._cmd_stop_recording.is_set()

def test_portal_toggle_mode_flips_on_press(monkeypatch):
    from talktype import app
    from talktype.input_backends import PortalInputBackend
    class Cfg: mode = "toggle"
    b = PortalInputBackend(Cfg())
    app._cmd_start_recording.clear(); app._cmd_stop_recording.clear()
    b._recording = False
    b._on_activated(None, None, None, None, None, _fake_params("dictate"))
    assert app._cmd_start_recording.is_set()   # first press starts
```

Add a `_fake_params(shortcut_id)` helper at the top of the test file returning an object whose `.unpack()` yields `(session_handle, shortcut_id, timestamp, {})` shaped like the portal signal.

- [ ] **Step 2: Run to verify it fails**

Run: `... -m pytest tests/test_backend_select.py -v` → FAIL (`_on_activated` NotImplementedError / attribute error).

- [ ] **Step 3: Implement PortalInputBackend**

Port `spikes/flatpak-portal/hotkey_portal.py` into the class: `start()` = build session bus, `register_app_id` is skipped in-sandbox (guard on `FLATPAK_ID`), CreateSession + BindShortcuts(`dictate`, description "TalkType: dictate"), subscribe `Activated`/`Deactivated` with `sender=None`, add a `GLib.timeout_add(50, tick)` that calls `app._service_tick(self.cfg, None, state)`, then `GLib.MainLoop().run()`. `_on_activated`: if `cfg.mode == "hold"` → `app._cmd_start_recording.set()`; else toggle `self._recording` and set start/stop accordingly. `_on_deactivated`: if `cfg.mode == "hold"` → `app._cmd_stop_recording.set()`; ignore in toggle mode.

- [ ] **Step 4: Run the suite**

Run: `... -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add src/talktype/input_backends.py tests/test_backend_select.py
git commit -m "flatpak(backend-b): PortalInputBackend — GlobalShortcuts hotkey -> _cmd events"
```

---

## Task 8: Wire backend selection into the service entry

Makes `app.py`'s service entry run the selected input backend instead of hard-calling `_loop_evdev`.

**Files:**
- Modify: `src/talktype/app.py` (the `_loop_evdev(cfg, input_device_idx)` call at line ~2679, inside `main()`)
- Test: existing suite (regression)

**Interfaces:**
- Consumes: `input_backends.get_input_backend`.

- [ ] **Step 1: Replace the hard call**

Change the final `_loop_evdev(cfg, input_device_idx)` in `main()` to:
```python
from .input_backends import get_input_backend
get_input_backend(cfg=cfg, input_device_idx=input_device_idx).start()
```
(Non-Flatpak → `EvdevInputBackend.start()` → `_loop_evdev(...)`, identical to before. Flatpak → `PortalInputBackend.start()`.)

- [ ] **Step 2: Run the suite + manual host dictation**

Run: `... -m pytest -q` → all pass. Run the dev app; confirm hold-to-talk still works (still Backend A on the host).

- [ ] **Step 3: Commit**

```bash
git add src/talktype/app.py
git commit -m "flatpak(backend-b): service entry runs the FLATPAK_ID-selected input backend"
```

---

## Task 9: End-to-end integration in the throwaway Flatpak

> **DEFERRED (2026-08-16) → real Flatpak manifest project.** Sizing showed the
> runtime (`org.gnome.Platform//48`, Python 3.12) lacks numpy/sounddevice/
> faster-whisper/evdev — all top-level `app.py` imports — so even a stubbed
> throwaway must bundle ~most of the real manifest's deps for a build we'd
> discard. The core risk (hotkey + typing inside a Flatpak) is already retired by
> the KDE spike. This validation moves into a dedicated manifest project (deps +
> NVIDIA GPU + onboarding parity + KDE/GNOME e2e). See
> `spikes/flatpak-portal/FINDINGS.md` → "BB-9 outcome".

Proves the whole thing: the real app, inside a Flatpak, dictates via portals on KDE, then GNOME. This is where Backend B is actually exercised.

**Files:**
- Create: `spikes/flatpak-portal/build_real_flatpak.sh`

- [ ] **Step 1: Write the wrapper-build script**

Model it on `spikes/flatpak-portal/build_spike_flatpak.sh`, but instead of copying the spike `.py` files, stage the whole app: `flatpak build-init` on `org.gnome.Platform//48` with app-id `io.github.ronb1964.TalkType`; copy `src/talktype` into `/app/lib/talktype` (and set `PYTHONPATH`); `build-finish` with `--socket=wayland --socket=fallback-x11 --share=ipc --socket=pulseaudio --talk-name=org.freedesktop.portal.Desktop --command=... `(a launcher that runs `python3 -m talktype.app`); export + install `--user`. Bundle only what the runtime lacks — faster-whisper/ctranslate2 handling is deferred (Task-9 test can point at a tiny/base model already cached, or stub the transcription to focus on input/output).

- [ ] **Step 2: Build + run on KDE (host)**

Run: `./spikes/flatpak-portal/build_real_flatpak.sh`, then `flatpak run --user io.github.ronb1964.TalkType`. Assign the `dictate` shortcut (KDE System Settings), approve the one-time remote-control dialog. Hold the key, speak, release. Acceptance: text is typed into a focused editor via libei, and the hotkey drove it via the portal — end to end, in the sandbox.

- [ ] **Step 3: GNOME cross-check**

Copy the build to a GNOME VM (Ubuntu or Fedora GNOME), repeat Step 2 (GNOME shows a shortcut picker instead of System Settings). Record any differences in `spikes/flatpak-portal/FINDINGS.md` (fill the "GNOME (VM)" column).

- [ ] **Step 4: Commit**

```bash
git add spikes/flatpak-portal/build_real_flatpak.sh spikes/flatpak-portal/FINDINGS.md
git commit -m "flatpak(backend-b): real-app throwaway-Flatpak integration test (KDE + GNOME)"
```

---

## Self-Review

**Spec coverage:**
- Backend A unchanged / add-don't-replace → Tasks 2, 6, 8 keep evdev+ydotool paths intact; Ydotool delegates to `_type_text`. ✓
- FLATPAK_ID selection → Task 1. ✓
- OutputBackend (ydotool + libei) → Tasks 1, 2, 5. ✓
- InputBackend (evdev + portal) → Tasks 1, 6, 7. ✓
- libei via ctypes, variadic/argtypes rules → Task 3. ✓
- portal_common, sender=None, no Registry in sandbox → Tasks 4, 7. ✓
- Session lifecycle + restore_token → Task 5. ✓
- Error surfacing (return False, never raise) → Tasks 5 (type_text guard). Recording-core notice on `type_text` False is existing behavior in `stop_recording`. ✓
- Testing: unit (1,2,3,4,7) + integration in throwaway Flatpak (9) + regression (6,8). ✓
- Out-of-scope (manifest/onboarding/GPU/Flathub) → not tasked. ✓

**Placeholder scan:** Portal/libei tasks (3,5,7) reference porting exact, proven files in `spikes/flatpak-portal/` with named adaptations — concrete, not "TODO". No forbidden placeholders.

**Type consistency:** `OutputBackend.type_text(text)->bool`, `get_output_backend`, `LibeiSession.type_string`/`pump_until_ready`, `InputBackend.start`, `_service_tick`, `_cmd_start_recording`/`_cmd_stop_recording`, `_on_activated`/`_on_deactivated` used consistently across tasks. ✓

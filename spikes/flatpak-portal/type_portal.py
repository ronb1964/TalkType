#!/usr/bin/env python3
"""RemoteDesktop portal -> ConnectToEIS -> libei -> type 'hello, world.'.

Handshake uses GDBus (gi.Gio). Keystroke transport uses libei via ctypes,
because Fedora ships libei.so.1 but no Ei GObject-Introspection typelib.
Run with a text editor focused; approve KDE's remote-control dialog.
"""
import ctypes as C
import select
import sys
import time

import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402
import _portal_common as pc  # noqa: E402

IFACE = "org.freedesktop.portal.RemoteDesktop"
KEYBOARD = 1  # RemoteDesktop DeviceType bitmask: KEYBOARD=1, POINTER=2

# --- libei enums (from upstream libei.h) ---
EI_EVENT_SEAT_ADDED = 3
EI_EVENT_DEVICE_ADDED = 5
EI_EVENT_DEVICE_RESUMED = 8
EI_DEVICE_CAP_KEYBOARD = 1 << 2  # = 4

# --- evdev keycodes (linux/input-event-codes.h) for our test string ---
KEY = {"h": 35, "e": 18, "l": 38, "o": 24, ",": 51, " ": 57,
       "w": 17, "r": 19, "d": 32, ".": 52}
TEST_STRING = "hello, world."


def _load_libei():
    ei = C.CDLL("libei.so.1")
    ei.ei_new_sender.restype = C.c_void_p
    ei.ei_new_sender.argtypes = [C.c_void_p]
    ei.ei_setup_backend_fd.restype = C.c_int
    ei.ei_setup_backend_fd.argtypes = [C.c_void_p, C.c_int]
    ei.ei_dispatch.argtypes = [C.c_void_p]
    ei.ei_get_event.restype = C.c_void_p
    ei.ei_get_event.argtypes = [C.c_void_p]
    ei.ei_get_fd.restype = C.c_int
    ei.ei_get_fd.argtypes = [C.c_void_p]
    ei.ei_now.restype = C.c_uint64
    ei.ei_now.argtypes = [C.c_void_p]
    ei.ei_event_get_type.restype = C.c_int
    ei.ei_event_get_type.argtypes = [C.c_void_p]
    ei.ei_event_get_seat.restype = C.c_void_p
    ei.ei_event_get_seat.argtypes = [C.c_void_p]
    ei.ei_event_get_device.restype = C.c_void_p
    ei.ei_event_get_device.argtypes = [C.c_void_p]
    ei.ei_event_unref.restype = C.c_void_p
    ei.ei_event_unref.argtypes = [C.c_void_p]
    # ei_seat_bind_capabilities is variadic (sentinel NULL) -> no argtypes
    ei.ei_device_start_emulating.argtypes = [C.c_void_p, C.c_uint32]
    ei.ei_device_keyboard_key.argtypes = [C.c_void_p, C.c_uint32, C.c_bool]
    ei.ei_device_frame.argtypes = [C.c_void_p, C.c_uint64]
    ei.ei_device_stop_emulating.argtypes = [C.c_void_p]
    return ei


def _emit_string(ei, ctx, dev):
    # ctx is the struct ei* context; ei is the CDLL. ei_now() needs the context.
    ei.ei_device_start_emulating(dev, 1)
    for ch in TEST_STRING:
        code = KEY[ch]
        ei.ei_device_keyboard_key(dev, code, True)
        ei.ei_device_frame(dev, ei.ei_now(ctx))
        ei.ei_device_keyboard_key(dev, code, False)
        ei.ei_device_frame(dev, ei.ei_now(ctx))
    ei.ei_device_stop_emulating(dev)


def _trace(msg):
    print(f"[libei] {msg}", flush=True)


def type_via_libei(fd):
    _trace(f"setting up on EIS fd {fd}")
    ei = _load_libei()
    _trace("loaded libei + signatures")
    ctx = ei.ei_new_sender(None)
    _trace(f"ei_new_sender -> {ctx!r}")
    if not ctx:
        print("[libei] ei_new_sender returned NULL"); return False
    rc = ei.ei_setup_backend_fd(ctx, fd)
    _trace(f"ei_setup_backend_fd -> rc={rc}")
    if rc != 0:
        print(f"[libei] ei_setup_backend_fd failed rc={rc}"); return False

    fd_ei = ei.ei_get_fd(ctx)
    _trace(f"ei_get_fd -> {fd_ei}")
    typed = False
    deadline = time.monotonic() + 10.0
    rounds = 0
    while time.monotonic() < deadline:
        select.select([fd_ei], [], [], 0.5)
        ei.ei_dispatch(ctx)
        rounds += 1
        if rounds <= 3:
            _trace(f"dispatch round {rounds} ok")
        while True:
            ev = ei.ei_get_event(ctx)
            if not ev:
                break
            etype = ei.ei_event_get_type(ev)
            if rounds <= 5:
                _trace(f"event type={etype}")
            if etype == EI_EVENT_SEAT_ADDED:
                seat = ei.ei_event_get_seat(ev)
                # ei_seat_bind_capabilities is variadic -> no argtypes, so pass
                # explicit ctypes objects or the 64-bit seat pointer truncates.
                ei.ei_seat_bind_capabilities(
                    C.c_void_p(seat), C.c_uint(EI_DEVICE_CAP_KEYBOARD),
                    C.c_void_p(0))
                _trace("bound keyboard capability on seat")
            elif etype == EI_EVENT_DEVICE_RESUMED and not typed:
                dev = ei.ei_event_get_device(ev)
                print("[libei] device resumed -> typing")
                _emit_string(ei, ctx, dev)
                typed = True
            ei.ei_event_unref(ev)
        if typed:
            # keep dispatching briefly so outgoing frames flush to the socket
            for _ in range(6):
                ei.ei_dispatch(ctx)
                time.sleep(0.05)
            print("[libei] done — check the editor")
            return True
    print("[libei] timed out before device was ready")
    return False


def main():
    bus = pc.session_bus()
    loop = GLib.MainLoop()
    st = {"session": None}

    def create_session():
        def b(token):
            opts = {"handle_token": GLib.Variant("s", token),
                    "session_handle_token": GLib.Variant("s", token + "_sess")}
            return GLib.Variant("(a{sv})", (opts,))
        pc.call_portal(bus, IFACE, "CreateSession", b, on_session)

    def on_session(code, results):
        if code:
            print(f"CreateSession failed {code}"); loop.quit(); return
        st["session"] = results["session_handle"]
        print(f"session: {st['session']}")
        select_devices()

    def select_devices():
        def b(token):
            opts = {"handle_token": GLib.Variant("s", token),
                    "types": GLib.Variant("u", KEYBOARD)}
            return GLib.Variant("(oa{sv})", (st["session"], opts))
        pc.call_portal(bus, IFACE, "SelectDevices", b,
                       lambda c, r: start() if not c else fail(c))

    def start():
        print("Approve KDE's remote-control dialog when it appears...")

        def b(token):
            opts = {"handle_token": GLib.Variant("s", token)}
            return GLib.Variant("(osa{sv})", (st["session"], "", opts))
        pc.call_portal(bus, IFACE, "Start", b,
                       lambda c, r: connect_eis() if not c else fail(c))

    def connect_eis():
        opts = GLib.Variant("(oa{sv})", (st["session"], {}))
        ret, fd_list = bus.call_with_unix_fd_list_sync(
            pc.BUS_NAME, pc.OBJ_PATH, IFACE, "ConnectToEIS", opts,
            GLib.VariantType("(h)"), Gio.DBusCallFlags.NONE, -1, None, None)
        fd_index = ret.unpack()[0]
        fd = fd_list.get(fd_index)
        print(f"EIS fd = {fd}")
        type_via_libei(fd)
        loop.quit()

    def fail(code):
        print(f"portal step failed {code}"); loop.quit()

    create_session()
    loop.run()


if __name__ == "__main__":
    sys.exit(main())

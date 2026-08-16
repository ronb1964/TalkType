"""libei access via ctypes — the sandbox-friendly way to emulate keystrokes.

Fedora (and the GNOME Flatpak runtime) ship libei.so.1 but no `Ei` GObject-
Introspection typelib, so we drive the C library directly with ctypes. This is
the productionized form of the proven spike code
(`spikes/flatpak-portal/type_portal.py`).

libei ctypes rules (learned the hard way in the spike):
- set restype/argtypes on every non-variadic call or 64-bit pointers truncate;
- ei_seat_bind_capabilities is variadic — pass explicit ctypes objects.
"""
import ctypes as C
import select
import time

# --- libei enums (from upstream libei.h) ---
EI_EVENT_SEAT_ADDED = 3
EI_EVENT_DEVICE_ADDED = 5
EI_EVENT_DEVICE_RESUMED = 8
EI_DEVICE_CAP_KEYBOARD = 1 << 2  # = 4

# --- evdev keycodes (linux/input-event-codes.h) ---
KEY_LEFTSHIFT = 42
KEY_SPACE = 57

_LETTERS = {
    "a": 30, "b": 48, "c": 46, "d": 32, "e": 18, "f": 33, "g": 34, "h": 35,
    "i": 23, "j": 36, "k": 37, "l": 38, "m": 50, "n": 49, "o": 24, "p": 25,
    "q": 16, "r": 19, "s": 31, "t": 20, "u": 22, "v": 47, "w": 17, "x": 45,
    "y": 21, "z": 44,
}
_DIGITS = {"1": 2, "2": 3, "3": 4, "4": 5, "5": 6,
           "6": 7, "7": 8, "8": 9, "9": 10, "0": 11}
# Unshifted punctuation (US layout) + space.
_PUNCT = {
    "-": 12, "=": 13, "[": 26, "]": 27, ";": 39, "'": 40, "`": 41, "\\": 43,
    ",": 51, ".": 52, "/": 53, " ": KEY_SPACE, "\t": 15,
}
# Shifted characters: char -> the base keycode you hold Shift with.
_SHIFTED = {
    "!": 2, "@": 3, "#": 4, "$": 5, "%": 6, "^": 7, "&": 8, "*": 9, "(": 10,
    ")": 11, "_": 12, "+": 13, "{": 26, "}": 27, ":": 39, '"': 40, "~": 41,
    "|": 43, "<": 51, ">": 52, "?": 53,
}

# char -> base evdev keycode (covers ASCII printable used in dictation output).
CHAR_TO_KEYCODE: dict[str, int] = {}
CHAR_TO_KEYCODE.update(_LETTERS)
CHAR_TO_KEYCODE.update(_DIGITS)
CHAR_TO_KEYCODE.update(_PUNCT)
CHAR_TO_KEYCODE.update(_SHIFTED)
for _c, _k in list(_LETTERS.items()):
    CHAR_TO_KEYCODE[_c.upper()] = _k  # uppercase shares the lowercase keycode

# Characters that require holding Shift while the base key is pressed.
SHIFT_CHARS: set[str] = set(_SHIFTED) | {c.upper() for c in _LETTERS}


def load_libei() -> C.CDLL:
    """Load libei.so.1 with all the argtypes/restypes set. Raises OSError if the
    library is not present."""
    for name in ("libei.so.1", "libei.so"):
        try:
            ei = C.CDLL(name)
            break
        except OSError:
            ei = None
    if ei is None:
        raise OSError("libei.so.1 not found")
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
    # ei_seat_bind_capabilities is variadic (sentinel NULL) -> no argtypes.
    ei.ei_device_start_emulating.argtypes = [C.c_void_p, C.c_uint32]
    ei.ei_device_keyboard_key.argtypes = [C.c_void_p, C.c_uint32, C.c_bool]
    ei.ei_device_frame.argtypes = [C.c_void_p, C.c_uint64]
    ei.ei_device_stop_emulating.argtypes = [C.c_void_p]
    try:  # keep the device alive across type_string calls (best-effort)
        ei.ei_device_ref.restype = C.c_void_p
        ei.ei_device_ref.argtypes = [C.c_void_p]
    except AttributeError:
        pass
    return ei


class LibeiSession:
    """Wraps an EIS connection (fd from the RemoteDesktop portal's ConnectToEIS)
    and types text through it. Keep one instance alive for the app's lifetime."""

    def __init__(self, fd: int):
        self.ei = load_libei()
        self.ctx = self.ei.ei_new_sender(None)
        if not self.ctx:
            raise RuntimeError("ei_new_sender returned NULL")
        rc = self.ei.ei_setup_backend_fd(self.ctx, fd)
        if rc != 0:
            raise RuntimeError(f"ei_setup_backend_fd failed rc={rc}")
        self.fd_ei = self.ei.ei_get_fd(self.ctx)
        self.device = None

    def pump_until_ready(self, timeout: float = 10.0) -> bool:
        """Run the ei event loop until the keyboard device is ready to emulate.
        Binds the keyboard capability on SEAT_ADDED and captures the device on
        DEVICE_RESUMED. Returns True once a device is available."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            select.select([self.fd_ei], [], [], 0.5)
            self.ei.ei_dispatch(self.ctx)
            while True:
                ev = self.ei.ei_get_event(self.ctx)
                if not ev:
                    break
                etype = self.ei.ei_event_get_type(ev)
                if etype == EI_EVENT_SEAT_ADDED:
                    seat = self.ei.ei_event_get_seat(ev)
                    # variadic call: explicit ctypes objects or the seat pointer
                    # truncates to 32 bits -> SIGSEGV.
                    self.ei.ei_seat_bind_capabilities(
                        C.c_void_p(seat), C.c_uint(EI_DEVICE_CAP_KEYBOARD),
                        C.c_void_p(0))
                elif etype == EI_EVENT_DEVICE_RESUMED:
                    dev = self.ei.ei_event_get_device(ev)
                    if hasattr(self.ei, "ei_device_ref"):
                        self.ei.ei_device_ref(dev)  # keep it alive
                    self.device = dev
                self.ei.ei_event_unref(ev)
            if self.device:
                return True
        return False

    def type_string(self, text: str) -> bool:
        """Type `text` via libei. Returns False if no device became ready."""
        if self.device is None and not self.pump_until_ready():
            return False
        ei, ctx, dev = self.ei, self.ctx, self.device
        ei.ei_device_start_emulating(dev, 1)
        for ch in text:
            kc = CHAR_TO_KEYCODE.get(ch)
            if kc is None:
                continue  # unsupported character; skip it
            shift = ch in SHIFT_CHARS
            if shift:
                ei.ei_device_keyboard_key(dev, KEY_LEFTSHIFT, True)
                ei.ei_device_frame(dev, ei.ei_now(ctx))
            ei.ei_device_keyboard_key(dev, kc, True)
            ei.ei_device_frame(dev, ei.ei_now(ctx))
            ei.ei_device_keyboard_key(dev, kc, False)
            ei.ei_device_frame(dev, ei.ei_now(ctx))
            if shift:
                ei.ei_device_keyboard_key(dev, KEY_LEFTSHIFT, False)
                ei.ei_device_frame(dev, ei.ei_now(ctx))
        ei.ei_device_stop_emulating(dev)
        # Keep dispatching briefly so the outgoing frames flush to the socket.
        for _ in range(6):
            ei.ei_dispatch(ctx)
            time.sleep(0.05)
        return True

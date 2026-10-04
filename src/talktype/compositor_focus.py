"""Ask the compositor which window has focus: Sway, i3, Hyprland, niri and X11.

Paste sends Ctrl+Shift+V to terminals (plain Ctrl+V is readline's
quoted-insert there and shows nothing), and some Electron apps get typed
instead of pasted. Both need the focused window's class. GNOME's extension
and KDE's KWin script push it to the tray; these compositors have nothing to
push it, but each answers the question over a local socket. So the dictation
service asks at paste time, when nobody has reported it (app.py,
_query_focused_window_class).

  Sway / i3   i3 IPC on $SWAYSOCK or $I3SOCK: GET_TREE, then the focused node.
              A native Wayland window has an app_id; an XWayland one has the
              X11 class instead.
  Hyprland    $XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket.sock,
              request "j/activewindow" (as hyprctl sends it); Hyprland replies
              and hangs up. It serves this socket synchronously and freezes
              while a connection stays open, so every request here is one
              short connection with a short timeout.
  niri        $NIRI_SOCKET, one line of JSON each way: "FocusedWindow".
  X11         XFCE, MATE, Cinnamon, LXQt, Openbox and the rest: the window
              manager names the focused window in the root window's
              _NET_ACTIVE_WINDOW (EWMH), and WM_CLASS gives its class. Only in
              an X11 session: under Wayland the service has a DISPLAY too
              (XWayland, for the recording indicator), but XWayland only knows
              the X11 apps and could name a window that doesn't have focus.
              Asked through XCB, not Xlib: Xlib reports a vanished window
              through a process-wide error handler whose default exits the
              program, and replacing it would fight GTK's own (the recording
              indicator runs GTK on X11 in this same process). XCB returns
              errors per request.

It's a hint for picking the paste shortcut, so anything going wrong means
"don't know" (None), quickly, and never an error.
"""
import ctypes
import json
import os
import socket
import struct

from .logger import setup_logger

logger = setup_logger(__name__)

TIMEOUT = 0.25      # seconds; these answer in about a millisecond

_I3_MAGIC = b"i3-ipc"
_I3_GET_TREE = 4


def _exchange(path, request, read_reply):
    """Connect to *path*, send *request*, return read_reply(sock); always closes."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(TIMEOUT)
        sock.connect(path)
        sock.sendall(request)
        return read_reply(sock)


def _recv_exact(sock, n):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("the compositor hung up mid-reply")
        data += chunk
    return data


def _recv_until_closed(sock):
    chunks = []
    while chunk := sock.recv(65536):
        chunks.append(chunk)
    return b"".join(chunks)


def _recv_line(sock):
    data = b""
    while not data.endswith(b"\n"):
        chunk = sock.recv(65536)
        if not chunk:
            break
        data += chunk
    return data


# --- Sway and i3 ---------------------------------------------------------------------

def _i3_reply(sock):
    head = _recv_exact(sock, 14)
    if head[:6] != _I3_MAGIC:
        raise ValueError("not an i3 IPC reply")
    length, _kind = struct.unpack("<II", head[6:])
    return json.loads(_recv_exact(sock, length))


def _find_focused(node):
    if node.get("focused"):
        return node
    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        found = _find_focused(child)
        if found:
            return found
    return None


def _from_i3(path):
    tree = _exchange(path, _I3_MAGIC + struct.pack("<II", 0, _I3_GET_TREE), _i3_reply)
    node = _find_focused(tree)
    if not node or node.get("type") not in ("con", "floating_con"):
        return None             # a workspace or output has focus, not a window
    return node.get("app_id") or (node.get("window_properties") or {}).get("class")


# --- Hyprland ------------------------------------------------------------------------

def _from_hyprland(signature):
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    path = os.path.join(runtime, "hypr", signature, ".socket.sock")
    window = json.loads(_exchange(path, b"j/activewindow", _recv_until_closed) or b"{}")
    return window.get("class") or window.get("initialClass")


# --- niri ----------------------------------------------------------------------------

def _from_niri(path):
    reply = json.loads(_exchange(path, b'"FocusedWindow"\n', _recv_line))
    window = (reply.get("Ok") or {}).get("FocusedWindow") or {}
    return window.get("app_id")


# --- X11 ----------------------------------------------------------------------------
# libxcb through ctypes. It's on every X11 system (Xlib itself is built on it),
# so this needs no new dependency.

_XCB_ATOM_WINDOW = 33           # predefined atoms (xproto)
_XCB_ATOM_WM_CLASS = 67
_XCB_GET_PROPERTY_TYPE_ANY = 0


class _Cookie(ctypes.Structure):
    _fields_ = [("sequence", ctypes.c_uint)]


class _ScreenIterator(ctypes.Structure):
    _fields_ = [("data", ctypes.c_void_p), ("rem", ctypes.c_int), ("index", ctypes.c_int)]


class _AtomReply(ctypes.Structure):
    _fields_ = [("response_type", ctypes.c_uint8), ("pad0", ctypes.c_uint8),
                ("sequence", ctypes.c_uint16), ("length", ctypes.c_uint32),
                ("atom", ctypes.c_uint32)]


_xcb = None


def _xcb_lib():
    """libxcb with the few signatures used here, loaded once."""
    global _xcb
    if _xcb is None:
        lib = ctypes.CDLL("libxcb.so.1")
        P, U8, U16, U32 = ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint32
        lib.xcb_connect.restype = P
        lib.xcb_connect.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
        lib.xcb_connection_has_error.argtypes = [P]
        lib.xcb_disconnect.argtypes = [P]
        lib.xcb_get_setup.restype = P
        lib.xcb_get_setup.argtypes = [P]
        lib.xcb_setup_roots_iterator.restype = _ScreenIterator
        lib.xcb_setup_roots_iterator.argtypes = [P]
        lib.xcb_screen_next.argtypes = [ctypes.POINTER(_ScreenIterator)]
        lib.xcb_intern_atom.restype = _Cookie
        lib.xcb_intern_atom.argtypes = [P, U8, U16, ctypes.c_char_p]
        lib.xcb_intern_atom_reply.restype = ctypes.POINTER(_AtomReply)
        lib.xcb_intern_atom_reply.argtypes = [P, _Cookie, ctypes.POINTER(P)]
        lib.xcb_get_property.restype = _Cookie
        lib.xcb_get_property.argtypes = [P, U8, U32, U32, U32, U32, U32]
        lib.xcb_get_property_reply.restype = P
        lib.xcb_get_property_reply.argtypes = [P, _Cookie, ctypes.POINTER(P)]
        lib.xcb_get_property_value.restype = P
        lib.xcb_get_property_value.argtypes = [P]
        lib.xcb_get_property_value_length.argtypes = [P]
        _xcb = lib
    return _xcb


_free = ctypes.CDLL(None).free
_free.argtypes = [ctypes.c_void_p]


def _x11_property(lib, conn, window, atom):
    """Raw bytes of *atom* on *window*, or None (an error, or not set)."""
    error = ctypes.c_void_p()
    cookie = lib.xcb_get_property(conn, 0, window, atom, _XCB_GET_PROPERTY_TYPE_ANY, 0, 1024)
    reply = lib.xcb_get_property_reply(conn, cookie, ctypes.byref(error))
    if error.value:
        _free(error)
    if not reply:
        return None
    try:
        length = lib.xcb_get_property_value_length(reply)
        return ctypes.string_at(lib.xcb_get_property_value(reply), length) if length > 0 else None
    finally:
        _free(reply)


def parse_wm_class(raw):
    """WM_CLASS holds the instance and class names, each ending in a NUL byte.
    Returns the class part, or the instance if
    that's all there is."""
    parts = [p.decode("utf-8", "replace") for p in raw.split(b"\0") if p]
    return parts[-1] if parts else None


def _from_x11():
    lib = _xcb_lib()
    screen_number = ctypes.c_int(0)
    conn = lib.xcb_connect(None, ctypes.byref(screen_number))   # $DISPLAY
    try:
        if not conn or lib.xcb_connection_has_error(conn):
            return None
        screens = lib.xcb_setup_roots_iterator(lib.xcb_get_setup(conn))
        for _ in range(screen_number.value):
            lib.xcb_screen_next(ctypes.byref(screens))
        if not screens.data:
            return None
        root = ctypes.c_uint32.from_address(screens.data).value   # xcb_screen_t starts with root

        name = b"_NET_ACTIVE_WINDOW"
        error = ctypes.c_void_p()
        atom_reply = lib.xcb_intern_atom_reply(
            conn, lib.xcb_intern_atom(conn, 1, len(name), name), ctypes.byref(error))
        if error.value:
            _free(error)
        if not atom_reply:
            return None
        active_atom = atom_reply.contents.atom
        _free(atom_reply)
        if not active_atom:
            return None             # no EWMH window manager running

        raw = _x11_property(lib, conn, root, active_atom)
        if not raw or len(raw) < 4:
            return None
        window = struct.unpack("=I", raw[:4])[0]
        if not window:
            return None             # nothing has focus (the desktop itself)
        wm_class = _x11_property(lib, conn, window, _XCB_ATOM_WM_CLASS)
        return parse_wm_class(wm_class) if wm_class else None
    finally:
        if conn:
            lib.xcb_disconnect(conn)


def _is_x11_session(env):
    session = (env.get("XDG_SESSION_TYPE") or "").lower()
    if session:
        return session == "x11"
    return bool(env.get("DISPLAY")) and not env.get("WAYLAND_DISPLAY")


def focused_class():
    """The focused window's class or app_id, or None if this isn't one of
    these desktops or it didn't answer."""
    env = os.environ
    try:
        if env.get("HYPRLAND_INSTANCE_SIGNATURE"):
            return _from_hyprland(env["HYPRLAND_INSTANCE_SIGNATURE"]) or None
        if env.get("NIRI_SOCKET"):
            return _from_niri(env["NIRI_SOCKET"]) or None
        path = env.get("SWAYSOCK") or env.get("I3SOCK")
        if path:
            return _from_i3(path) or None
        if _is_x11_session(env):
            return _from_x11() or None
    except Exception as e:
        logger.debug(f"Could not ask the compositor for the focused window: {e}")
    return None

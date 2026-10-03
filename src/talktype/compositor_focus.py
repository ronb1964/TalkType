"""Ask the compositor which window has focus, on Sway, i3, Hyprland and niri.

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

It's a hint for picking the paste shortcut, so anything going wrong means
"don't know" (None), quickly, and never an error.
"""
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


def focused_class():
    """The focused window's class or app_id, or None if this isn't one of
    these compositors or it didn't answer."""
    env = os.environ
    try:
        if env.get("HYPRLAND_INSTANCE_SIGNATURE"):
            return _from_hyprland(env["HYPRLAND_INSTANCE_SIGNATURE"]) or None
        if env.get("NIRI_SOCKET"):
            return _from_niri(env["NIRI_SOCKET"]) or None
        path = env.get("SWAYSOCK") or env.get("I3SOCK")
        if path:
            return _from_i3(path) or None
    except Exception as e:
        logger.debug(f"Could not ask the compositor for the focused window: {e}")
    return None

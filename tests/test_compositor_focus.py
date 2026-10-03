"""Asking Sway, i3, Hyprland and niri which window has focus.

Each test runs a stand-in compositor on a real Unix socket that speaks that
compositor's real protocol, so the framing, the parsing and the clean-up are
all exercised. The real compositors were checked by hand (headless, in a
container) when this module was written.
"""
import json
import socket
import struct
import threading

import pytest

from talktype import compositor_focus as cf


def _serve(path, handler):
    """Answer one connection on *path* with *handler(conn)*, in the background."""
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)

    def run():
        conn, _ = server.accept()
        with conn:
            handler(conn)
        server.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def _clear_env(monkeypatch):
    for var in ("SWAYSOCK", "I3SOCK", "HYPRLAND_INSTANCE_SIGNATURE", "NIRI_SOCKET"):
        monkeypatch.delenv(var, raising=False)


# --- Sway and i3 -------------------------------------------------------------------

# Trimmed from a real `swaymsg -t get_tree`: the focused window can sit deep in
# the tree, in floating_nodes, and an XWayland window has no app_id.
def _tree(focused):
    foot = {"type": "con", "app_id": "foot", "focused": focused == "foot", "nodes": [],
            "floating_nodes": []}
    xterm = {"type": "con", "app_id": None, "focused": focused == "xterm",
             "window_properties": {"class": "XTerm", "instance": "xterm"},
             "nodes": [], "floating_nodes": []}
    workspace = {"type": "workspace", "focused": focused == "workspace",
                 "nodes": [{"type": "con", "focused": False, "nodes": [foot],
                            "floating_nodes": []}],
                 "floating_nodes": [xterm]}
    return {"type": "root", "focused": False, "nodes": [
        {"type": "output", "focused": False, "nodes": [workspace], "floating_nodes": []}]}


def _i3_server(tree):
    def handler(conn):
        head = conn.recv(14)
        assert head[:6] == b"i3-ipc"
        length, kind = struct.unpack("<II", head[6:])
        assert kind == 4                                   # GET_TREE
        body = json.dumps(tree).encode()
        conn.sendall(b"i3-ipc" + struct.pack("<II", len(body), 4) + body)
    return handler


@pytest.mark.parametrize("focused, expected", [
    ("foot", "foot"),                   # native Wayland: app_id
    ("xterm", "XTerm"),                 # XWayland: the X11 class
    ("workspace", None),                # an empty workspace has focus, no window
])
def test_sway_reports_the_focused_window(tmp_path, monkeypatch, focused, expected):
    _clear_env(monkeypatch)
    path = tmp_path / "sway.sock"
    done = _serve(path, _i3_server(_tree(focused)))
    monkeypatch.setenv("SWAYSOCK", str(path))
    assert cf.focused_class() == expected
    done.join(1)


def test_i3_uses_the_same_protocol(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    path = tmp_path / "i3.sock"
    done = _serve(path, _i3_server(_tree("foot")))
    monkeypatch.setenv("I3SOCK", str(path))
    assert cf.focused_class() == "foot"
    done.join(1)


# --- Hyprland ----------------------------------------------------------------------

def test_hyprland_reports_the_focused_window_and_hangs_up(tmp_path, monkeypatch):
    """Hyprland answers its socket synchronously and freezes the desktop while
    a connection stays open, so the request must be one write and the
    connection closed straight after the reply."""
    _clear_env(monkeypatch)
    signature = "abc123_1700000000_42"
    folder = tmp_path / "hypr" / signature
    folder.mkdir(parents=True)
    got = []

    def handler(conn):
        got.append(conn.recv(100))
        conn.sendall(json.dumps({"class": "com.mitchellh.ghostty",
                                 "initialClass": "com.mitchellh.ghostty"}).encode())

    done = _serve(folder / ".socket.sock", handler)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", signature)
    assert cf.focused_class() == "com.mitchellh.ghostty"
    assert got == [b"j/activewindow"]
    done.join(1)


def test_hyprland_with_nothing_focused(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    folder = tmp_path / "hypr" / "sig"
    folder.mkdir(parents=True)
    done = _serve(folder / ".socket.sock", lambda conn: (conn.recv(100), conn.sendall(b"{}")))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "sig")
    assert cf.focused_class() is None
    done.join(1)


# --- niri --------------------------------------------------------------------------

def test_niri_reports_the_focused_window(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    got = []

    def handler(conn):
        got.append(conn.recv(100))
        conn.sendall(b'{"Ok":{"FocusedWindow":{"id":12,"title":"~","app_id":"Alacritty",'
                     b'"workspace_id":6,"is_focused":true}}}\n')

    path = tmp_path / "niri.sock"
    done = _serve(path, handler)
    monkeypatch.setenv("NIRI_SOCKET", str(path))
    assert cf.focused_class() == "Alacritty"
    assert got == [b'"FocusedWindow"\n']
    done.join(1)


def test_niri_with_nothing_focused(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    path = tmp_path / "niri.sock"
    done = _serve(path, lambda conn: (conn.recv(100),
                                      conn.sendall(b'{"Ok":{"FocusedWindow":null}}\n')))
    monkeypatch.setenv("NIRI_SOCKET", str(path))
    assert cf.focused_class() is None
    done.join(1)


# --- never in the way --------------------------------------------------------------

def test_no_compositor_socket_means_unknown(monkeypatch):
    _clear_env(monkeypatch)
    assert cf.focused_class() is None


def test_a_dead_socket_means_unknown(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SWAYSOCK", str(tmp_path / "gone.sock"))
    assert cf.focused_class() is None


def test_a_compositor_that_never_answers_is_given_up_on_quickly(tmp_path, monkeypatch):
    import time
    _clear_env(monkeypatch)
    path = tmp_path / "stuck.sock"
    release = threading.Event()
    done = _serve(path, lambda conn: release.wait(5))
    monkeypatch.setenv("SWAYSOCK", str(path))
    started = time.monotonic()
    assert cf.focused_class() is None
    assert time.monotonic() - started < 1.0
    release.set()
    done.join(1)


# --- where the dictation service uses it ---------------------------------------------

def test_the_service_asks_the_compositor_when_nobody_reported_focus(monkeypatch):
    from talktype import app
    monkeypatch.setattr(app, "_get_tray_dbus_proxy", lambda: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(cf, "focused_class", lambda: "foot")
    assert app._query_focused_window_class() == "foot"


def test_a_reported_window_wins_over_asking_the_compositor(monkeypatch):
    from talktype import app

    class Tray:
        def GetFocusedWindowClass(self, **kw):
            return "org.kde.konsole"

    monkeypatch.setattr(app, "_get_tray_dbus_proxy", lambda: Tray())
    monkeypatch.setattr(cf, "focused_class", lambda: pytest.fail("asked the compositor"))
    assert app._query_focused_window_class() == "org.kde.konsole"


@pytest.mark.parametrize("app_id", [
    "com.mitchellh.ghostty", "org.gnome.Console", "xfce4-terminal",
    "com.system76.CosmicTerm", "Kitty", "foot",
])
def test_terminals_common_on_tiling_desktops_get_terminal_paste(app_id):
    from talktype.app import is_terminal_class
    assert is_terminal_class(app_id)

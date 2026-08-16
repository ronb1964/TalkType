"""Minimal GDBus helper for the xdg-desktop-portal Request/Response pattern."""
import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

BUS_NAME = "org.freedesktop.portal.Desktop"
OBJ_PATH = "/org/freedesktop/portal/desktop"
APP_ID = "io.github.ronb1964.TalkType"
_counter = 0


def register_app_id(bus, app_id: str = APP_ID) -> None:
    """xdg-desktop-portal >=1.21 requires non-Flatpak apps to declare their app
    id via the host Registry before using GlobalShortcuts/RemoteDesktop. Older
    portals lack this interface and infer the id, so a failure here is non-fatal.
    Inside a real Flatpak the id is supplied automatically and this is skipped."""
    try:
        bus.call_sync(BUS_NAME, OBJ_PATH, "org.freedesktop.host.portal.Registry",
                      "Register", GLib.Variant("(sa{sv})", (app_id, {})),
                      None, Gio.DBusCallFlags.NONE, -1, None)
        print(f"[registry] registered app id: {app_id}")
    except GLib.GError as e:
        print(f"[registry] Register skipped ({e.message})")


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
    results:dict) is invoked when the Request's Response signal arrives."""
    token = new_request_token()
    request_path = (f"/org/freedesktop/portal/desktop/request/"
                    f"{_sender_prefix(bus)}/{token}")

    def _on_signal(conn, sender, path, iface_, signal, params):
        code, results = params.unpack()
        on_response(code, results)

    bus.signal_subscribe(BUS_NAME, "org.freedesktop.portal.Request", "Response",
                         request_path, None, Gio.DBusSignalFlags.NONE, _on_signal)
    bus.call_sync(BUS_NAME, OBJ_PATH, iface, method, param_builder(token),
                  None, Gio.DBusCallFlags.NONE, -1, None)

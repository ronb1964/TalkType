"""Minimal GDBus helper for the xdg-desktop-portal Request/Response pattern.

Productionized from spikes/flatpak-portal/_portal_common.py. Both the input
(GlobalShortcuts) and output (RemoteDesktop) backends use this to talk to the
portal over the session bus.
"""
import logging

import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

logger = logging.getLogger(__name__)

BUS_NAME = "org.freedesktop.portal.Desktop"
OBJ_PATH = "/org/freedesktop/portal/desktop"
APP_ID = "io.github.ronb1964.TalkType"
_counter = 0


def register_app_id(bus, app_id: str = APP_ID) -> None:
    """xdg-desktop-portal >=1.21 requires non-Flatpak apps to declare their app
    id via the host Registry before GlobalShortcuts. Inside a real Flatpak the id
    is supplied automatically and Register is refused — so this is a no-op there
    and callers skip it when FLATPAK_ID is set. Failure here is non-fatal."""
    try:
        bus.call_sync(BUS_NAME, OBJ_PATH, "org.freedesktop.host.portal.Registry",
                      "Register", GLib.Variant("(sa{sv})", (app_id, {})),
                      None, Gio.DBusCallFlags.NONE, -1, None)
        logger.info("Registered app id with the host portal Registry: %s", app_id)
    except GLib.GError as e:
        logger.debug("Registry.Register skipped: %s", e.message)


def new_request_token() -> str:
    global _counter
    _counter += 1
    return f"talktype_{_counter}"


def session_bus() -> Gio.DBusConnection:
    return Gio.bus_get_sync(Gio.BusType.SESSION, None)


def _sender_prefix(bus) -> str:
    # unique name ":1.234" -> "1_234" per the portal Request path convention
    return bus.get_unique_name().lstrip(":").replace(".", "_")


def call_portal(bus, iface, method, param_builder, on_response):
    """Issue a portal request and invoke on_response(code:int, results:dict) when
    its Response signal arrives. param_builder(handle_token) returns the method's
    IN args as a GLib.Variant, embedding handle_token in the options a{sv}."""
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

#!/usr/bin/env python3
"""Bind a global shortcut via the portal and log press/release. Ctrl+C to quit."""
import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402
import _portal_common as pc  # noqa: E402

# The GlobalShortcuts portal (esp. on KDE) requires the caller to have an app
# id. For a non-sandboxed process the portal resolves it from the program name
# -> a matching .desktop file. Set it before touching the bus.
GLib.set_prgname("io.github.ronb1964.TalkType")
GLib.set_application_name("TalkType")

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
            print(f"CreateSession failed: {code}")
            loop.quit()
            return
        state["session"] = results["session_handle"]
        print(f"session: {state['session']}")
        bind()

    def bind():
        # one shortcut "dictate", suggest F8; desktop draws its own dialog
        shortcuts = GLib.Variant("a(sa{sv})", [
            ("dictate", {
                "description": GLib.Variant("s", "TalkType: hold to dictate"),
                "preferred_trigger": GLib.Variant("s", "F8")})])

        def builder(token):
            opts = {"handle_token": GLib.Variant("s", token)}
            return GLib.Variant("(oa(sa{sv})sa{sv})",
                                (state["session"], shortcuts, "", opts))
        pc.call_portal(bus, IFACE, "BindShortcuts", builder, on_bound)

    def on_bound(code, results):
        if code != 0:
            print(f"BindShortcuts failed/cancelled: {code}")
            loop.quit()
            return
        print("bound. Now HOLD then RELEASE your chosen key. Ctrl+C to quit.")

    def on_activated(conn, s, p, i, sig, params):
        print(f"  >>> Activated   {params.unpack()[1]}")

    def on_deactivated(conn, s, p, i, sig, params):
        print(f"  >>> Deactivated {params.unpack()[1]}")

    bus.signal_subscribe(pc.BUS_NAME, IFACE, "Activated", None, None,
                         Gio.DBusSignalFlags.NONE, on_activated)
    bus.signal_subscribe(pc.BUS_NAME, IFACE, "Deactivated", None, None,
                         Gio.DBusSignalFlags.NONE, on_deactivated)
    pc.register_app_id(bus)   # portal >=1.21 needs this before CreateSession
    create_session()
    loop.run()


if __name__ == "__main__":
    main()

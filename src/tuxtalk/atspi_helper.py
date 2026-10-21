"""Whether the cursor is in a password field, asked of the accessibility bus
(AT-SPI), so a dictation is never typed into one.

Plain D-Bus calls on a connection of TuxTalk's own (Gio), not libatspi: the
AppImage doesn't ship libatspi's typelib, and libatspi shares one bus
connection with GTK's own accessibility bridge, which the GTK thread of the
dictation service dispatches while this runs on another thread.

Which apps answer (tried 2026-10-20): GTK 3 and GTK 4 apps always. Qt (KDE
apps) and Firefox only while accessibility is switched on, by a screen reader
or the desktop's accessibility setting. Chromium-based browsers and Electron
apps (Brave, Discord, VS Code) only if it was on when they started
(ACCESSIBILITY_ENABLED=1 or the desktop setting); turned on later, they need
a restart. An app that doesn't answer, a slow bus or none at all counts as
"not a password field", so typing goes ahead as it always did.
"""

import logging
import time

from gi.repository import Gio, GLib

logger = logging.getLogger(__name__)

# The whole question is given this long, each D-Bus call a part of it: an
# app that hangs must not hold up the dictation waiting to be typed.
BUDGET_S = 0.25
CALL_TIMEOUT_MS = 100

_ROOT = "/org/a11y/atspi/accessible/root"
_REGISTRY = "org.a11y.atspi.Registry"
_ACCESSIBLE = "org.a11y.atspi.Accessible"
_COLLECTION = "org.a11y.atspi.Collection"

# AtspiStateType and AtspiRole numbers (at-spi2-core's atspi-constants.h).
_STATE_ACTIVE = 1
_STATE_FOCUSED = 12
_STATE_SHOWING = 25
_ROLE_PASSWORD_TEXT = 40

# The shell's own "window" is always active; the focus is in an app's.
_SKIPPED_APPS = {"gnome-shell"}

_bus = None


class _OutOfTime(Exception):
    pass


def focused_is_password() -> bool:
    """True when the focused widget of the active window is a password field.
    False when it isn't, and whenever that can't be found out in BUDGET_S."""
    started = time.monotonic()
    try:
        bus = _a11y_bus()
        if bus is None:
            return False
        deadline = started + BUDGET_S
        for window in _active_windows(bus, deadline):
            focused = _focused_in(bus, window, deadline)
            if focused is not None:
                return _call(bus, focused, _ACCESSIBLE, "GetRole", None, deadline)[0] \
                    == _ROLE_PASSWORD_TEXT
        return False
    except _OutOfTime:
        logger.info(f"Password field check: no answer in {BUDGET_S}s, typing as usual")
        return False
    except GLib.Error as e:
        logger.debug(f"Password field check: the accessibility bus didn't answer: {e.message}")
        return False
    except Exception as e:
        # An app answering in a shape nobody expected: the dictation is
        # still typed, as before this check existed.
        logger.warning(f"Password field check failed, typing as usual: {e!r}")
        return False
    finally:
        logger.debug(f"Password field check took {time.monotonic() - started:.3f}s")


def _a11y_bus():
    """TuxTalk's own connection to the accessibility bus, or None without one."""
    global _bus
    if _bus is not None and not _bus.is_closed():
        return _bus
    session = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    address = session.call_sync(
        "org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus", "GetAddress", None,
        GLib.VariantType("(s)"), Gio.DBusCallFlags.NO_AUTO_START, CALL_TIMEOUT_MS, None)[0]
    if not address:
        return None
    _bus = Gio.DBusConnection.new_for_address_sync(
        address,
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
        | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None, None)
    return _bus


def _call(bus, node, interface, method, args, deadline):
    """One call on the accessible *node*, a (bus name, path) pair."""
    left_ms = int((deadline - time.monotonic()) * 1000)
    if left_ms <= 0:
        raise _OutOfTime
    reply = bus.call_sync(node[0], node[1], interface, method, args, None,
                          Gio.DBusCallFlags.NO_AUTO_START,
                          min(CALL_TIMEOUT_MS, left_ms), None)
    return reply.unpack()


def _children(bus, node, deadline):
    return _call(bus, node, _ACCESSIBLE, "GetChildren", None, deadline)[0]


def _states(bus, node, deadline) -> int:
    """The state set as one number: bit n is AtspiStateType n."""
    low, high = _call(bus, node, _ACCESSIBLE, "GetState", None, deadline)[0]
    return low | high << 32


def _active_windows(bus, deadline):
    for app in _children(bus, (_REGISTRY, _ROOT), deadline):
        try:
            if _call(bus, app, "org.freedesktop.DBus.Properties", "Get",
                     GLib.Variant("(ss)", (_ACCESSIBLE, "Name")), deadline)[0] \
                    in _SKIPPED_APPS:
                continue
            windows = _children(bus, app, deadline)
        except GLib.Error:
            continue    # an app that quit or hangs; the next one may be it
        for window in windows:
            try:
                if _states(bus, window, deadline) & 1 << _STATE_ACTIVE:
                    yield window
            except GLib.Error:
                continue


def _focused_in(bus, window, deadline):
    """The focused widget inside *window*, or None."""
    # Every part of the rule is "match all" (1): at-spi2-atk turns any other
    # match type on an empty part, even "invalid", into "no match".
    rule = GLib.Variant("((aiia{ss}iaiiasib)uib)", (
        ([1 << _STATE_FOCUSED, 0], 1, {}, 1, [0, 0, 0, 0], 1, [], 1, False),
        1, 1, True))    # in tree order, one match, the whole window
    try:
        found = _call(bus, window, _COLLECTION, "GetMatches", rule, deadline)[0]
        return found[0] if found else None
    except GLib.Error:
        # Qt has no Collection interface: walk the visible widgets instead.
        return _walk_for_focus(bus, window, deadline)


def _walk_for_focus(bus, node, deadline):
    for child in _children(bus, node, deadline):
        states = _states(bus, child, deadline)
        if states & 1 << _STATE_FOCUSED:
            return child
        if states & 1 << _STATE_SHOWING:
            found = _walk_for_focus(bus, child, deadline)
            if found is not None:
                return found
    return None

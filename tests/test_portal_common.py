"""Basic checks for the portal GDBus helper. The live D-Bus calls need a running
portal and are exercised by the Flatpak integration test (BB-9)."""
from tuxtalk import portal_common as pc


def test_request_tokens_are_unique_and_prefixed():
    a, b = pc.new_request_token(), pc.new_request_token()
    assert a != b
    assert a.startswith("talktype_") and not a.startswith("talktype_spike_")


def test_constants():
    assert pc.BUS_NAME == "org.freedesktop.portal.Desktop"
    assert pc.OBJ_PATH == "/org/freedesktop/portal/desktop"


# --- the Response subscription ---------------------------------------------

import threading  # noqa: E402

from gi.repository import GLib  # noqa: E402


class FakeBus:
    """Records signal subscriptions; call_sync can be told to fail."""

    def __init__(self, fail_call=False):
        self.subs = {}
        self._next = 1
        self.fail_call = fail_call

    def get_unique_name(self):
        return ":1.42"

    def signal_subscribe(self, sender, iface, member, path, arg0, flags, callback):
        sid, self._next = self._next, self._next + 1
        self.subs[sid] = callback
        return sid

    def signal_unsubscribe(self, sid):
        del self.subs[sid]          # KeyError on a double unsubscribe

    def call_sync(self, *args):
        if self.fail_call:
            raise GLib.Error("refused")

    def respond(self, code, results):
        (callback,) = self.subs.values()
        callback(self, pc.BUS_NAME, "/path", "org.freedesktop.portal.Request", "Response",
                 GLib.Variant("(ua{sv})", (code, results)))


def _builder(token):
    return GLib.Variant("(a{sv})", ({},))


def test_the_subscription_ends_when_the_response_arrives():
    """Otherwise every request leaves a live Response subscription on the shared bus."""
    bus, got = FakeBus(), []
    cancel = pc.call_portal(bus, "I", "M", _builder, lambda c, r: got.append(c))
    bus.respond(0, {})
    assert got == [0] and bus.subs == {}
    cancel()                        # already gone: does nothing


def test_the_subscription_ends_when_the_call_fails():
    bus = FakeBus(fail_call=True)
    try:
        pc.call_portal(bus, "I", "M", _builder, lambda c, r: None)
    except GLib.Error:
        pass
    assert bus.subs == {}


def test_an_error_in_the_response_handler_reaches_on_error():
    """PyGObject would swallow it, and a caller waiting for the response would hang."""
    bus, errors = FakeBus(), []
    pc.call_portal(bus, "I", "M", _builder, lambda c, r: r["missing"],
                   on_error=errors.append)
    bus.respond(0, {})
    assert len(errors) == 1 and isinstance(errors[0], KeyError)


def test_tokens_stay_unique_across_threads():
    tokens = []

    def take():
        tokens.extend(pc.new_request_token() for _ in range(2000))
    threads = [threading.Thread(target=take) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(tokens)) == len(tokens)

"""Basic checks for the portal GDBus helper. The live D-Bus calls need a running
portal and are exercised by the Flatpak integration test (BB-9)."""
from talktype import portal_common as pc


def test_request_tokens_are_unique_and_prefixed():
    a, b = pc.new_request_token(), pc.new_request_token()
    assert a != b
    assert a.startswith("talktype_") and not a.startswith("talktype_spike_")


def test_constants():
    assert pc.BUS_NAME == "org.freedesktop.portal.Desktop"
    assert pc.OBJ_PATH == "/org/freedesktop/portal/desktop"
    assert pc.APP_ID == "io.github.ronb1964.TalkType"

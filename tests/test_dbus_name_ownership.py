"""The tray, not the dictation service, owns TalkType's D-Bus name.

Both register the name. They used to request it the same way, so the
service queued behind the tray and inherited the name whenever the tray
restarted while the service kept running. The GNOME extension's menu then
reached the service's stub, which had no FixWordInDictation ("unknown
method", 2026-09-29), and the service's recording-state reports went to
itself instead of the tray.

Runs real processes on a private bus (dbus-run-session), so it never touches
the desktop session's TalkType.
"""
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

pytestmark = pytest.mark.skipif(not shutil.which("dbus-run-session"),
                                reason="needs dbus-run-session")

ROLE = textwrap.dedent("""
    import sys
    from gi.repository import GLib
    from talktype.dbus_service import TalkTypeDBusService
    class App: pass
    try:
        TalkTypeDBusService(App(), primary=(sys.argv[1] == "tray"))
        print("registered", flush=True)
    except Exception as e:
        print(type(e).__name__, flush=True)   # the service keeps running anyway
    GLib.MainLoop().run()
""")

DRIVER = textwrap.dedent("""
    import subprocess, sys, time, dbus
    ROLE = sys.argv[1]
    bus = dbus.SessionBus()
    NAME = "io.github.ronb1964.TalkType"

    def start(role):
        p = subprocess.Popen([sys.executable, "-c", ROLE, role],
                             stdout=subprocess.PIPE, text=True)
        p.first_line = p.stdout.readline().strip()
        return p

    def owner():
        time.sleep(0.3)
        try:
            return bus.call_blocking("org.freedesktop.DBus", "/org/freedesktop/DBus",
                "org.freedesktop.DBus", "GetConnectionUnixProcessID", "s", (NAME,))
        except dbus.exceptions.DBusException:
            return None

    def who(procs):
        o = owner()
        return next((name for name, p in procs.items() if p.pid == o), o)

    # 1. Normal start: tray first, then the service it launches.
    tray = start("tray"); svc = start("service")
    print("normal", who({"tray": tray, "service": svc}), svc.first_line)

    # 2. The tray restarts while the service keeps running.
    tray.kill(); tray.wait()
    print("tray_gone", who({"service": svc}))
    tray2 = start("tray")
    print("tray_back", who({"tray": tray2, "service": svc}))
    tray2.kill(); svc.kill()

    # 3. No tray running: the service stands in, then a tray takes over.
    svc = start("service")
    print("standalone", who({"service": svc}), svc.first_line)
    tray = start("tray")
    print("tray_takes_over", who({"tray": tray, "service": svc}))
    tray.kill(); svc.kill()
""")


def test_tray_owns_the_name_and_the_service_never_inherits_it(tmp_path):
    driver = tmp_path / "driver.py"
    driver.write_text(DRIVER)
    out = subprocess.run(
        ["dbus-run-session", "--", sys.executable, str(driver), ROLE],
        capture_output=True, text=True, timeout=60, env=os.environ.copy())
    lines = dict(line.split(" ", 1) for line in out.stdout.splitlines() if " " in line)
    assert lines.get("normal") == "tray NameExistsException", out.stdout + out.stderr
    assert lines.get("tray_gone") == "None", "the service inherited the name"
    assert lines.get("tray_back") == "tray"
    assert lines.get("standalone") == "service registered"
    assert lines.get("tray_takes_over") == "tray"

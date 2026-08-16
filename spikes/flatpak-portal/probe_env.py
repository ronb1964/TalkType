#!/usr/bin/env python3
"""Report portal + libei availability on this machine. Read-only; no injection."""
import ctypes
import os
import re
import shutil
import subprocess


def parse_portal_version(version_str: str) -> tuple[int, int]:
    """Parse 'x.y...' out of an rpm/version string. (0, 0) if unrecognised."""
    m = re.match(r"(\d+)\.(\d+)", version_str.strip())
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _portal_version() -> str:
    for cmd in (["rpm", "-q", "--qf", "%{VERSION}", "xdg-desktop-portal"],
                ["dpkg-query", "-W", "-f=${Version}", "xdg-desktop-portal"]):
        if shutil.which(cmd[0]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True,
                                     timeout=5).stdout
                if out.strip():
                    return out.strip()
            except Exception:
                pass
    return "unknown"


def _has_gi_ei() -> bool:
    try:
        import gi
        gi.require_version("Ei", "1.0")
        from gi.repository import Ei  # noqa: F401
        return True
    except Exception:
        return False


def _libei_soname() -> str | None:
    for name in ("libei.so.1", "libei.so"):
        try:
            ctypes.CDLL(name)
            return name
        except OSError:
            continue
    return None


def _portal_iface_present(iface: str) -> bool:
    """Introspect the portal object for an interface name via gdbus."""
    try:
        out = subprocess.run(
            ["gdbus", "introspect", "--session",
             "--dest", "org.freedesktop.portal.Desktop",
             "--object-path", "/org/freedesktop/portal/desktop"],
            capture_output=True, text=True, timeout=10).stdout
        return iface in out
    except Exception:
        return False


def main():
    ver = _portal_version()
    maj, minr = parse_portal_version(ver)
    print("=== TalkType Flatpak portal-input probe ===")
    print(f"session type      : {os.environ.get('XDG_SESSION_TYPE', '<unset>')}")
    print(f"desktop           : {os.environ.get('XDG_CURRENT_DESKTOP', '<unset>')}")
    print(f"wayland display   : {os.environ.get('WAYLAND_DISPLAY', '<unset>')}")
    print(f"xdg-desktop-portal: {ver}  -> ({maj}.{minr}) "
          f"libei-portal floor >=1.21: {'OK' if (maj, minr) >= (1, 21) else 'TOO OLD'}")
    print(f"libei .so         : {_libei_soname() or 'NOT FOUND'}")
    print(f"gi.repository.Ei  : {'available' if _has_gi_ei() else 'NOT available (expect ctypes/helper)'}")
    print(f"RemoteDesktop portal : {'present' if _portal_iface_present('org.freedesktop.portal.RemoteDesktop') else 'MISSING'}")
    print(f"GlobalShortcuts portal: {'present' if _portal_iface_present('org.freedesktop.portal.GlobalShortcuts') else 'MISSING'}")


if __name__ == "__main__":
    main()

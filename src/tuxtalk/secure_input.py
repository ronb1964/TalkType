"""Setting up hotkeys and typing without the "input" group.

TuxTalk used to ask for the user to be put in the "input" group: hotkeys
need to read the keyboard, and typing needs /dev/uinput. That group lets
every program the user runs read every key, passwords included.

This sets up the safer way, in the same single password prompt:

1. The hotkey helper (hotkey_helper.py) as a system service. It reads the
   keyboards under a throwaway user (systemd's DynamicUser) that has no
   network, no home folder, a read-only system and no way to gain more
   rights, and tells the user at the screen only about hotkeys.
2. A udev rule that gives /dev/uinput to the user at the screen (logind's
   "uaccess"), the way Steam does for its controller support. Programs can
   then make a virtual keyboard to type with, but /dev/uinput can't be used
   to read anything.

Nothing needs a restart: the service starts at once, and logind grants the
uinput access as soon as udev re-applies its rules.

The helper is copied to a root-owned folder, so no program the user runs
can change what the service runs. The install script goes to pkexec on
standard input, never through a file the user's programs could edit while
the password dialog is open.
"""
import os
import subprocess

from .logger import setup_logger

logger = setup_logger(__name__)

SERVICE = "tuxtalk-hotkeys.service"
HELPER_DIR = "/usr/local/libexec/tuxtalk"
HELPER_PATH = f"{HELPER_DIR}/tuxtalk-hotkeys"
UNIT_PATH = f"/etc/systemd/system/{SERVICE}"
UINPUT_RULE_PATH = "/etc/udev/rules.d/70-tuxtalk-uinput.rules"
PYTHON = "/usr/bin/python3"

# Numbered below 73, where systemd's 73-seat-late.rules turns the uaccess tag
# into an access list for the user at the screen.
UINPUT_RULE = """\
# TuxTalk: the user at the screen may create virtual keyboards (to type
# dictated text), as Steam's 60-steam-input.rules does. /dev/uinput can't be
# used to read keys. Remove this file, or uninstall from TuxTalk, to undo it.
KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"
"""

UNIT = f"""\
[Unit]
Description=TuxTalk hotkey helper (tells TuxTalk about its hotkeys, nothing else)
Documentation=https://github.com/ronb1964/TuxTalk

[Service]
Type=simple
ExecStart={PYTHON} -I -S {HELPER_PATH}
Restart=on-failure
RestartSec=2

# A throwaway user whose only extra right is reading the keyboards.
DynamicUser=yes
SupplementaryGroups=input
RuntimeDirectory=tuxtalk-hotkeys
RuntimeDirectoryMode=0755
UMask=0077

# Nothing else: no devices but input ones, no network, no home folders, no
# writing anywhere but its own folder in /run, no way to gain privileges.
DevicePolicy=closed
DeviceAllow=char-input rw
PrivateNetwork=yes
RestrictAddressFamilies=AF_UNIX
IPAddressDeny=any
ProtectHome=yes
ProtectSystem=strict
PrivateTmp=yes
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectClock=yes
ProtectHostname=yes
ProtectProc=invisible
ProcSubset=pid
LockPersonality=yes
MemoryDenyWriteExecute=yes
RestrictRealtime=yes
RestrictNamespaces=yes
RestrictSUIDSGID=yes
SystemCallArchitectures=native
SystemCallFilter=@system-service
SystemCallFilter=~@privileged @resources @mount @swap @reboot @raw-io @module @obsolete

[Install]
WantedBy=multi-user.target
"""

PKEXEC_TIMEOUT = 300


def helper_source():
    """The helper as it's installed: this TuxTalk's own hotkey_helper.py."""
    from . import hotkey_helper
    with open(hotkey_helper.__file__, encoding="utf-8") as f:
        return f.read()


def _heredoc(path, content, delimiter):
    if delimiter in content:
        raise ValueError(f"{delimiter} appears in the content for {path}")
    return f"cat > {path} <<'{delimiter}'\n{content}{'' if content.endswith(chr(10)) else chr(10)}{delimiter}\n"


def install_script():
    """The script pkexec runs as root to set it all up."""
    return f"""set -euo pipefail
install -d -m 0755 -o root -g root {HELPER_DIR}
tmp=$(mktemp {HELPER_DIR}/.tuxtalk-hotkeys.XXXXXX)
{_heredoc('"$tmp"', helper_source(), "TUXTALK_HELPER_EOF")}chown root:root "$tmp"
chmod 0755 "$tmp"
mv -f "$tmp" {HELPER_PATH}
{_heredoc(UNIT_PATH, UNIT, "TUXTALK_UNIT_EOF")}chmod 0644 {UNIT_PATH}
{_heredoc(UINPUT_RULE_PATH, UINPUT_RULE, "TUXTALK_RULE_EOF")}chmod 0644 {UINPUT_RULE_PATH}
systemctl daemon-reload
systemctl enable {SERVICE}
# restart, not start: a TuxTalk update brings a new helper with it
systemctl restart {SERVICE}
udevadm control --reload-rules
udevadm trigger --action=change --sysname-match=uinput
for i in $(seq 50); do
    [ -S /run/tuxtalk-hotkeys/hotkeys.sock ] && exit 0
    sleep 0.1
done
echo "The hotkey helper didn't start. See: journalctl -u {SERVICE}" >&2
exit 1
"""


def uninstall_script():
    """The script pkexec runs as root to take it all away again."""
    return f"""set -uo pipefail
systemctl disable --now {SERVICE} 2>/dev/null
rm -f {UNIT_PATH} {HELPER_PATH} {UINPUT_RULE_PATH}
rmdir --ignore-fail-on-non-empty {HELPER_DIR} 2>/dev/null
systemctl daemon-reload
udevadm control --reload-rules
udevadm trigger --action=change --sysname-match=uinput
exit 0
"""


def can_install():
    """(True, "") when this system can run the helper, else (False, why).
    Without it, setup falls back to the "input" group."""
    if os.environ.get("FLATPAK_ID"):
        return False, "the Flatpak uses the desktop's portals instead"
    if not os.path.isdir("/run/systemd/system"):
        return False, "this system doesn't run systemd"
    if not os.path.isdir("/run/systemd/seats"):
        return False, "logind isn't tracking who's at the screen"
    try:
        ok = subprocess.run([PYTHON, "-I", "-S", "-c",
                             "import sys; sys.exit(sys.version_info < (3, 8))"],
                            timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    if not ok:
        return False, f"{PYTHON} (3.8 or newer) isn't installed"
    if not any(os.access(os.path.join(d, "pkexec"), os.X_OK)
               for d in ("/usr/bin", "/bin", "/usr/local/bin")):
        return False, "pkexec isn't installed"
    return True, ""


def is_installed():
    return os.path.exists(UNIT_PATH) and os.path.exists(HELPER_PATH)


def running_version():
    """The running helper's version, from its hello, or None."""
    from .hotkey_helper_client import HelperKeyboard
    keyboard = HelperKeyboard()
    try:
        if not os.path.exists(keyboard.socket_path) or not keyboard.connect():
            return None
        return keyboard.helper_version
    finally:
        keyboard.close()


def needs_update():
    """Installed, but older than the helper this TuxTalk brings."""
    from .hotkey_helper import VERSION
    running = running_version()
    return is_installed() and running is not None and running != VERSION


def _run_as_root(script, what):
    """(ok, message) after running *script* through pkexec."""
    from .uinput_helper import pkexec_was_declined
    try:
        result = subprocess.run(["pkexec", "/bin/bash", "-s"], input=script, text=True,
                                capture_output=True, timeout=PKEXEC_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, "That took too long. Please try again."
    except FileNotFoundError:
        return False, "pkexec isn't installed, so TuxTalk can't ask for your password."
    if result.returncode == 0:
        logger.info(f"Hotkey helper {what}")
        return True, ""
    if pkexec_was_declined(result):
        logger.info(f"Hotkey helper {what}: cancelled at the password prompt")
        return False, "cancelled"
    detail = (result.stderr or result.stdout or "").strip()
    logger.error(f"Hotkey helper {what} failed: {detail}")
    return False, detail or "it failed for an unknown reason"


def install_with_pkexec():
    """Install (or update) the helper and the typing rule. (ok, message)."""
    return _run_as_root(install_script(), "installed")


def uninstall_with_pkexec():
    """Remove the helper and the typing rule. (ok, message)."""
    return _run_as_root(uninstall_script(), "removed")

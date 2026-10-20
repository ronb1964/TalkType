#!/bin/sh
# Runs as root before the .deb or .rpm is removed (fpm --before-remove).
#
# TuxTalk's first run sets up two system pieces that live outside the
# package, so the package manager doesn't know about them: the hotkey helper
# (a copy in /usr/local/libexec, run by its own systemd service) and the udev
# rules that let the user type. They outlive the package unless removed here,
# and the helper would go on reading the keyboard for nobody.
#
# Only on a real removal: dpkg calls this with "upgrade" and rpm with 1 when
# a new version replaces this one, and the helper must stay for that.
# Home folders are the user's (Debian policy), so their settings and models
# stay; Preferences -> Updates & Backup -> Uninstall TuxTalk removes those.
# The same paths as secure_input.py and uinput_helper.py
# (tests/test_uninstall.py checks they match).

case "$1" in
    remove|0) ;;
    *) exit 0 ;;
esac

if command -v systemctl >/dev/null 2>&1; then
    systemctl disable --now tuxtalk-hotkeys.service >/dev/null 2>&1 || true
fi
rm -f /etc/systemd/system/tuxtalk-hotkeys.service \
      /usr/local/libexec/tuxtalk/tuxtalk-hotkeys \
      /etc/udev/rules.d/70-tuxtalk-uinput.rules \
      /etc/udev/rules.d/99-talktype-uinput.rules
rmdir /usr/local/libexec/tuxtalk 2>/dev/null || true
if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload >/dev/null 2>&1 || true
fi
if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules >/dev/null 2>&1 || true
    udevadm trigger --action=change --sysname-match=uinput >/dev/null 2>&1 || true
fi
exit 0

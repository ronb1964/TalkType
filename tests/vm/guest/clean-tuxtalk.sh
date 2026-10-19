#!/bin/bash
# Takes every trace of TuxTalk (and the old TalkType) off a test VM, so the
# "clean" snapshot taken afterwards is a computer that has never seen it.
# Run once per VM by `run.py prepare`; the release runs never need it, they
# revert to the snapshot instead.
#
# The hotkey helper is root's, so removing it needs sudo. A VM without
# passwordless sudo just reports that and keeps going: it must not prompt.
set -u

# Stop anything running from an AppImage or the helper's client first. The
# pattern is assembled so it never matches this script's own command line.
app="[T]uxTalk|[T]alkType|[t]uxtalk|[t]alktype"
ps -eo pid=,args= | grep -E "$app" | grep -v clean-tuxtalk | awk '{print $1}' | xargs -r kill 2>/dev/null
sleep 1

rm -rf ~/AppImages/TuxTalk* ~/AppImages/TalkType*
rm -rf ~/.config/tuxtalk ~/.config/talktype
rm -rf ~/.local/share/TuxTalk ~/.local/share/TalkType ~/.local/share/tuxtalk ~/.local/share/talktype
rm -rf ~/.cache/huggingface ~/.cache/tuxtalk ~/.cache/talktype
rm -f ~/.config/autostart/tuxtalk.desktop ~/.config/autostart/talktype.desktop
rm -f ~/.local/share/applications/tuxtalk*.desktop ~/.local/share/applications/talktype*.desktop
find ~/.local/share/icons -name 'tuxtalk*' -delete 2>/dev/null
find ~/.local/share/icons -name 'talktype*' -delete 2>/dev/null
if command -v gnome-extensions >/dev/null; then
    gnome-extensions uninstall talktype@ronb1964.github.io 2>/dev/null
fi
rm -rf ~/.local/share/gnome-shell/extensions/talktype@ronb1964.github.io

if [ -e /etc/systemd/system/tuxtalk-hotkeys.service ] || [ -d /usr/local/libexec/tuxtalk ]; then
    if sudo -n true 2>/dev/null; then
        sudo -n systemctl disable --now tuxtalk-hotkeys 2>/dev/null
        sudo -n rm -rf /etc/systemd/system/tuxtalk-hotkeys.service /usr/local/libexec/tuxtalk \
            /etc/udev/rules.d/70-tuxtalk-uinput.rules
        sudo -n systemctl daemon-reload
        echo "hotkey helper removed"
    else
        echo "hotkey helper is installed and sudo needs a password: remove it by hand" >&2
        exit 1
    fi
fi
echo "clean"

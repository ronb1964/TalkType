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
# Copies older test rounds and the Flatpak trial (2026-08) left behind;
# uninstall checks count anything named TuxTalk or TalkType as a leftover.
rm -rf ~/.config/tuxtalk.bak* ~/.config/talktype.bak* ~/.config/autostart/talktype.desktop.bak*
rm -f ~/.config/autostart/io.github.ronb1964.T*.desktop
if command -v flatpak >/dev/null; then
    flatpak uninstall --user -y --noninteractive io.github.ronb1964.TalkType >/dev/null 2>&1
    flatpak remotes --user --columns=name 2>/dev/null | grep -i -E 'talktype|tuxtalk' |
        xargs -r -n1 flatpak remote-delete --user --force 2>/dev/null
fi
rm -rf ~/.var/app/io.github.ronb1964.TalkType ~/.var/app/io.github.ronb1964.TuxTalk
rm -rf ~/tt-test ~/kit/TuxTalk* ~/kit/TalkType* ~/run*-bak ~/tt-keyd    # hand testing
rm -rf ~/.local/share/TuxTalk.bak* ~/.local/share/TalkType*.bak*
rm -rf ~/.local/share/flatpak/repo/refs/heads/deploy/app/io.github.ronb1964.T* \
    ~/.local/share/flatpak/repo/refs/remotes/talktype-origin
rm -f ~/.local/share/applications/tuxtalk*.desktop ~/.local/share/applications/talktype*.desktop
find ~/.local/share/icons -name 'tuxtalk*' -delete 2>/dev/null
find ~/.local/share/icons -name 'talktype*' -delete 2>/dev/null
if command -v gnome-extensions >/dev/null; then
    gnome-extensions uninstall talktype@ronb1964.github.io 2>/dev/null
fi
rm -rf ~/.local/share/gnome-shell/extensions/talktype@ronb1964.github.io

# A run leaves its pkexec stand-in behind (checks_firstrun), and with it
# first run sets typing up silently: no prompt for the checks to see.
if grep -qs "Test-VM stand-in for pkexec" /usr/local/bin/pkexec; then
    if sudo -n rm -f /usr/local/bin/pkexec; then
        echo "pkexec stand-in removed"
    else
        echo "the pkexec stand-in is installed and sudo needs a password: remove it by hand" >&2
        exit 1
    fi
fi

# The 0.15 test round (2026-10-13) let polkit approve everything without a
# password, so pkexec never showed the prompt the first-run checks look for.
if sudo -n test -e /etc/polkit-1/rules.d/49-nopasswd.rules; then
    sudo -n rm -f /etc/polkit-1/rules.d/49-nopasswd.rules && echo "polkit no-password rule removed"
fi

# Before the hotkey helper (0.16), setup put the user in the input group
# with a uinput rule of its own. A VM still set up that way types without
# Fix Typing, so first run never offers the helper the checks look for.
if [ -e /etc/udev/rules.d/99-talktype-uinput.rules ] || id -nG | grep -qw input; then
    if sudo -n true 2>/dev/null; then
        sudo -n rm -f /etc/udev/rules.d/99-talktype-uinput.rules
        sudo -n gpasswd -d "$USER" input
        if getent group input | cut -d: -f4 | tr , '\n' | grep -qx "$USER"; then
            echo "still in the input group after gpasswd: remove it by hand" >&2
            exit 1
        fi
        echo "input group and old uinput rule removed (takes effect at the next boot)"
    else
        echo "the old input-group setup is here and sudo needs a password: remove it by hand" >&2
        exit 1
    fi
fi

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

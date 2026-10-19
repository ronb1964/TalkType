#!/bin/bash
# Gives a test VM two pretend microphones on PipeWire, so dictation can be
# tested with no person speaking:
#   tt_mic       hears whatever is played into the tt_voice sink
#                (pw-play --target tt_voice phrase.wav); the default input.
#   tt_quiet_mic hears nothing at all, for the "only silence" warning.
# Safe to run twice: modules already loaded are left alone.
set -eu

have() { pactl list short sources | awk '{print $2}' | grep -qx "$1"; }

if ! have tt_mic; then
    pactl load-module module-null-sink sink_name=tt_voice \
        sink_properties=device.description=TT-Voice >/dev/null
    pactl load-module module-remap-source master=tt_voice.monitor source_name=tt_mic \
        source_properties=device.description=TT-Microphone >/dev/null
fi
if ! have tt_quiet_mic; then
    pactl load-module module-null-sink sink_name=tt_quiet \
        sink_properties=device.description=TT-Quiet >/dev/null
    pactl load-module module-remap-source master=tt_quiet.monitor source_name=tt_quiet_mic \
        source_properties=device.description=TT-Quiet-Microphone >/dev/null
fi
pactl set-default-source "${1:-tt_mic}"
pactl set-source-volume tt_mic 100%
pactl get-default-source

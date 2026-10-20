#!/bin/bash
# Test-VM stand-in for pkexec, installed as /usr/local/bin/pkexec only AFTER the
# harness has seen the real password prompt appear (and cancelled it). It runs
# the same root script through the VM's passwordless sudo, which exists only
# on the test VMs, so the rest of first-run can go on with nobody typing a
# password. Every call is logged: one call means one password prompt for a
# real user.
echo "$(date '+%H:%M:%S') $*" >> ~/tt/pkexec-calls.log
exec sudo -n env PKEXEC_UID="$(id -u)" "$@"

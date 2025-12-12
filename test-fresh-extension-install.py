#!/usr/bin/env python3
"""
Test the exact extension installation flow from first-run.
This simulates what happens during the welcome dialog.
"""

import os
import sys

# Set up path like run-dev.sh does
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
sys.path.insert(1, '/usr/lib64/python3.13/site-packages')
sys.path.insert(2, '/usr/lib/python3.13/site-packages')

from talktype import extension_helper

print("=" * 70)
print("TESTING FRESH EXTENSION INSTALLATION")
print("=" * 70)

print("\n1. Checking extension status BEFORE installation:")
status = extension_helper.get_extension_status()
print(f"   Available (GNOME): {status['available']}")
print(f"   Installed: {status['installed']}")
print(f"   Enabled: {status['enabled']}")

if status['installed']:
    print("\n   ❌ Extension already installed! Please run:")
    print("      gnome-extensions uninstall talktype@ronb1964.github.io")
    sys.exit(1)

print("\n2. Downloading and installing extension...")
print("   (This simulates what happens during welcome dialog)")

def progress_cb(msg, percent):
    print(f"   [{percent:3d}%] {msg}")

success = extension_helper.download_and_install_extension(progress_callback=progress_cb)

print(f"\n3. Installation result: {'✅ SUCCESS' if success else '❌ FAILED'}")

print("\n4. Checking extension status AFTER installation:")
status = extension_helper.get_extension_status()
print(f"   Installed: {status['installed']}")
print(f"   Enabled: {status['enabled']}")

# Check gsettings directly
import subprocess
result = subprocess.run(
    ['gsettings', 'get', 'org.gnome.shell', 'enabled-extensions'],
    capture_output=True,
    text=True
)
enabled_list = result.stdout.strip()
in_gsettings = 'talktype@ronb1964.github.io' in enabled_list

print(f"\n5. Checking gsettings directly:")
print(f"   In enabled-extensions list: {in_gsettings}")
if in_gsettings:
    print("   ✅ Extension IS in gsettings (will persist across logout!)")
else:
    print("   ❌ Extension NOT in gsettings (will NOT persist across logout!)")

print(f"\n6. Extension info:")
result = subprocess.run(
    ['gnome-extensions', 'info', 'talktype@ronb1964.github.io'],
    capture_output=True,
    text=True
)
for line in result.stdout.split('\n'):
    if 'Enabled:' in line or 'State:' in line:
        print(f"   {line}")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)

if success and status['enabled'] and in_gsettings:
    print("✅ PASS: Extension installed, enabled, and will persist!")
elif success and status['installed'] and in_gsettings:
    print("⚠️  PARTIAL: Extension installed and in gsettings, but shows as not enabled")
    print("   (May need logout to activate)")
else:
    print("❌ FAIL: Extension not properly installed/enabled")

print("\nTo test persistence: logout and login, then check:")
print("   gnome-extensions info talktype@ronb1964.github.io")

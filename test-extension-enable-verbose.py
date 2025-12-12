#!/usr/bin/env python3
"""Test extension enabling with verbose output."""

import os
import sys
import subprocess

# Set up path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from talktype import desktop_detect

EXTENSION_UUID = 'talktype@ronb1964.github.io'

print("=" * 60)
print("Testing Extension Enable")
print("=" * 60)

print("\n1. Current extension status:")
print(f"   Installed: {desktop_detect.is_extension_installed(EXTENSION_UUID)}")
print(f"   Enabled: {desktop_detect.is_extension_enabled(EXTENSION_UUID)}")

print("\n2. Disabling extension first...")
result = subprocess.run(
    ['gnome-extensions', 'disable', EXTENSION_UUID],
    capture_output=True,
    text=True
)
print(f"   Return code: {result.returncode}")
if result.stdout:
    print(f"   stdout: {result.stdout}")
if result.stderr:
    print(f"   stderr: {result.stderr}")

print("\n3. Checking status after disable:")
print(f"   Enabled: {desktop_detect.is_extension_enabled(EXTENSION_UUID)}")

print("\n4. Enabling extension using desktop_detect.enable_extension()...")
success = desktop_detect.enable_extension(EXTENSION_UUID)
print(f"   Result: {success}")

print("\n5. Checking status after enable:")
print(f"   Enabled: {desktop_detect.is_extension_enabled(EXTENSION_UUID)}")

print("\n6. Checking gsettings:")
result = subprocess.run(
    ['gsettings', 'get', 'org.gnome.shell', 'enabled-extensions'],
    capture_output=True,
    text=True
)
enabled_list = result.stdout.strip()
print(f"   enabled-extensions: {enabled_list}")
print(f"   Contains talktype: {EXTENSION_UUID in enabled_list}")

print("\n" + "=" * 60)

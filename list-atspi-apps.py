#!/usr/bin/env python3
"""
Simple script to list all applications visible to AT-SPI.
Run this with VS Code open to see if it appears.
"""

import gi
gi.require_version('Atspi', '2.0')
from gi.repository import Atspi

desktop = Atspi.get_desktop(0)
app_count = desktop.get_child_count()

print(f"AT-SPI can see {app_count} applications:\n")

for i in range(app_count):
    try:
        app = desktop.get_child_at_index(i)
        if app:
            name = app.get_name() or "(unnamed)"
            print(f"{i+1}. {name}")
    except Exception:
        print(f"{i+1}. (error reading app)")

print("\n✅ If you don't see VS Code in this list, it means VS Code doesn't")
print("   expose itself to AT-SPI (common for Electron apps).")

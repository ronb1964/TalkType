#!/usr/bin/env python3
"""Test script to show welcome dialog and adjust height."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Set up environment for system PyGObject
sys.path.insert(0, '/usr/lib64/python3.13/site-packages')
sys.path.insert(0, '/usr/lib/python3.13/site-packages')

from talktype.welcome_dialog import WelcomeDialog

# Test scenario 4 (GNOME + NVIDIA)
print("Showing scenario 4 welcome dialog (GNOME + NVIDIA)")
print("Current height: 1220px")
print("\nCheck if there's any scrolling...")

dialog = WelcomeDialog(force_gnome=True, force_nvidia=True)
result = dialog.run()
dialog.destroy()

print(f"\nResult: {result}")

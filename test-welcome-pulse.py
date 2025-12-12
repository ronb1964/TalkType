#!/usr/bin/env python3
"""Test welcome dialog checkbox pulse animation."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Set up environment for system PyGObject
sys.path.insert(0, '/usr/lib64/python3.13/site-packages')
sys.path.insert(0, '/usr/lib/python3.13/site-packages')

from talktype.welcome_dialog import WelcomeDialog

print("Showing welcome dialog scenario 4 (GNOME + NVIDIA) to test checkbox pulse...")

dialog = WelcomeDialog(force_gnome=True, force_nvidia=True)
result = dialog.run()
dialog.destroy()

print(f"\nResult: {result}")

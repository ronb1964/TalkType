#!/usr/bin/env python3
"""Test script to show Tips dialog WITHOUT extension reminder"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

# Import the tips dialog
from talktype.welcome_dialog import show_tips_and_features_dialog

if __name__ == '__main__':
    Gtk.init(None)

    # Show the dialog with extension_installed=False (no yellow glow, no logout text)
    selected_model = show_tips_and_features_dialog(extension_installed=False)

    print(f"Selected model: {selected_model}")

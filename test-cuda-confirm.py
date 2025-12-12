#!/usr/bin/env python3
"""
Test CUDA download confirmation dialog from tray menu.
This simulates clicking "Download CUDA Libraries" from the tray menu.
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_tray_cuda_confirm():
    """Test the tray menu CUDA download confirmation dialog."""
    from talktype.tray import DictationTray

    # Create a minimal tray instance
    tray = DictationTray()

    # Call the download_cuda method (simulates menu click)
    print("Testing tray menu CUDA download confirmation...")
    print("You should see a confirmation dialog asking if you want to download.")
    print("Click 'No' to test cancellation (don't actually download).")

    tray.download_cuda(None)

    print("\nTest complete!")
    print("If you clicked 'No', check the terminal for 'CUDA download cancelled by user'")

if __name__ == "__main__":
    test_tray_cuda_confirm()

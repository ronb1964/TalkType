#!/usr/bin/env python3
"""
Test CUDA download cancellation.
This opens the download progress dialog and you should click Cancel to test it.
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_cuda_cancel():
    """Test the CUDA download cancellation."""
    from talktype import cuda_helper

    print("Testing CUDA download cancellation...")
    print("A progress dialog will appear.")
    print("Click the 'Cancel' button or the X to test cancellation.")
    print("")

    # Call the download dialog
    result = cuda_helper.show_cuda_download_dialog()

    print("\n" + "="*50)
    if result is None:
        print("✅ SUCCESS: Download was cancelled (returned None)")
    elif result is True:
        print("⚠️  Download completed successfully (returned True)")
    else:
        print("❌ Download failed (returned False)")
    print("="*50)

if __name__ == "__main__":
    test_cuda_cancel()

#!/usr/bin/env python3
"""
Test model download progress dialog.
This will check if tiny model is cached, and if not, show progress dialog.
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_model_download():
    """Test the model download progress dialog."""
    from talktype.model_helper import is_model_cached, download_model_with_progress

    model_name = "tiny"
    print(f"Testing model download for: {model_name}")
    print("="*50)

    # Check if model is cached
    if is_model_cached(model_name):
        print(f"✅ Model '{model_name}' is already cached")
        print("   No download needed - loading directly...")
    else:
        print(f"⏳ Model '{model_name}' not cached - will show progress dialog")

    # Try to download/load with progress
    print("\nAttempting to load model...")
    model = download_model_with_progress(model_name, device="cpu", compute_type="int8")

    print("\n" + "="*50)
    if model is None:
        print("❌ Model load cancelled or failed")
    else:
        print(f"✅ Model loaded successfully!")
        print(f"   Type: {type(model)}")
    print("="*50)

if __name__ == "__main__":
    test_model_download()

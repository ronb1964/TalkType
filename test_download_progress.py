#!/usr/bin/env python3
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

def test_download():
    from talktype.model_helper import download_model_with_progress, is_model_cached
    model_name = "small"  # 244MB
    print(f"Testing: {model_name}, cached: {is_model_cached(model_name)}")
    if is_model_cached(model_name):
        print("Already cached!")
        return
    model = download_model_with_progress(model_name, device="cpu", show_confirmation=True)
    print(f"Result: {'Success' if model else 'Failed/Cancelled'}")

def main():
    t = threading.Thread(target=test_download)
    t.start()
    t.join()  # Wait for thread to complete
    print("Done!")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Test script for the unified download progress dialog.
Shows a demo with two simulated download tasks.
"""

import sys
import time
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

# Add src to path for imports
sys.path.insert(0, 'src')

from talktype.download_progress_dialog import UnifiedDownloadDialog, DownloadTask


def simulate_cuda_download(progress_callback, cancel_event):
    """Simulate CUDA library download with realistic progress."""
    steps = [
        ("Downloading nvidia-cuda-runtime-cu12...", 0),
        ("Downloading nvidia-cuda-runtime-cu12... 25%", 10),
        ("Downloading nvidia-cuda-runtime-cu12... 50%", 20),
        ("Downloading nvidia-cuda-runtime-cu12... 100%", 23),
        ("Downloading nvidia-cublas-cu12...", 23),
        ("Downloading nvidia-cublas-cu12... 25%", 30),
        ("Downloading nvidia-cublas-cu12... 50%", 40),
        ("Downloading nvidia-cublas-cu12... 100%", 46),
        ("Downloading nvidia-cudnn-cu12...", 46),
        ("Downloading nvidia-cudnn-cu12... 25%", 55),
        ("Downloading nvidia-cudnn-cu12... 50%", 65),
        ("Downloading nvidia-cudnn-cu12... 100%", 70),
        ("Extracting CUDA libraries...", 70),
        ("Extracting nvidia_cuda_runtime... (1/3)", 75),
        ("Extracting nvidia_cublas... (2/3)", 85),
        ("Extracting nvidia_cudnn... (3/3)", 95),
        ("CUDA libraries installed successfully!", 100),
    ]

    for message, percent in steps:
        if cancel_event.is_set():
            print("CUDA download cancelled")
            return False

        progress_callback(message, percent)
        time.sleep(0.4)  # Simulate download time

    return True


def simulate_extension_install(progress_callback, cancel_event):
    """Simulate GNOME extension installation."""
    steps = [
        ("Downloading extension from GitHub...", 20),
        ("Extracting extension files...", 50),
        ("Installing to ~/.local/share/gnome-shell/extensions/...", 80),
        ("Extension installed successfully!", 100),
    ]

    for message, percent in steps:
        if cancel_event.is_set():
            print("Extension install cancelled")
            return False

        progress_callback(message, percent)
        time.sleep(0.3)  # Simulate install time

    return True


def main():
    """Run the test."""
    Gtk.init(sys.argv)

    print("=" * 60)
    print("Testing Unified Download Dialog")
    print("=" * 60)
    print("\nThis demo shows:")
    print("  • Two download tasks running simultaneously")
    print("  • Individual progress bars for each task")
    print("  • Individual cancel buttons")
    print("  • Auto-close when all tasks complete")
    print("\nTry canceling one task while letting the other continue!")
    print("=" * 60)

    # Create the dialog
    dialog = UnifiedDownloadDialog()

    # Add CUDA download task
    cuda_task = DownloadTask(
        name="CUDA Libraries",
        description="GPU acceleration libraries",
        size_text="~800MB",
        download_func=simulate_cuda_download
    )
    dialog.add_task(cuda_task)

    # Add extension install task
    extension_task = DownloadTask(
        name="GNOME Extension",
        description="Native desktop integration",
        size_text="~3KB",
        download_func=simulate_extension_install
    )
    dialog.add_task(extension_task)

    # Run the dialog
    results = dialog.run()

    # Print results
    print("\n" + "=" * 60)
    print("Download Results:")
    print("=" * 60)
    for task_name, result in results.items():
        status = "✅ SUCCESS" if result['success'] else ("❌ CANCELLED" if result['cancelled'] else "❌ FAILED")
        print(f"{task_name}: {status}")
    print("=" * 60)


if __name__ == '__main__':
    main()

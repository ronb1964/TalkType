#!/usr/bin/env python3
"""
CUDA Helper Module for TalkType AppImage
Handles NVIDIA GPU detection and CUDA library downloads
"""

import os
import sys
import subprocess
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from .logger import setup_logger

logger = setup_logger(__name__)

# Timeout constants (in seconds)
NVIDIA_SMI_TIMEOUT = 5
SUBPROCESS_TIMEOUT = 2

# UI delay constants (in milliseconds)
SUCCESS_DIALOG_DELAY_MS = 1000
ERROR_DIALOG_DELAY_MS = 2000

def detect_nvidia_gpu():
    """Check if NVIDIA GPU is present using nvidia-smi."""
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
                              capture_output=True, text=True, timeout=NVIDIA_SMI_TIMEOUT)
        return result.returncode == 0 and result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def has_cuda_libraries():
    """
    Check if CUDA libraries are available for running GPU-accelerated models.
    This checks:
    1. Downloaded CUDA in ~/.local/share/TalkType/cuda (preferred for AppImage)
    2. System-wide CUDA installation (standard /usr paths)
    3. CUDA toolkit installation (/usr/local/cuda, /opt/cuda)
    """
    # First check for downloaded CUDA libraries in AppImage location
    # This is the preferred location for AppImage users
    cuda_path = os.path.expanduser("~/.local/share/TalkType/cuda")
    lib_path = os.path.join(cuda_path, "lib")
    
    if os.path.exists(lib_path):
        # Check for key CUDA libraries
        required_libs = ['libcudart.so', 'libcublas.so']
        found_all = True
        
        for lib in required_libs:
            try:
                result = subprocess.run(['find', lib_path, '-name', f'{lib}*'],
                                      capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT)
                if not result.stdout.strip():
                    found_all = False
                    break
            except (subprocess.TimeoutExpired, Exception):
                found_all = False
                break
        
        if found_all:
            return True
    
    # Check system-wide CUDA installation via ldconfig (most reliable)
    try:
        result = subprocess.run(['ldconfig', '-p'], capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT)
        has_cudart = 'libcudart.so' in result.stdout
        has_cublas = 'libcublas.so' in result.stdout
        has_cudnn = 'libcudnn.so' in result.stdout

        # If we have basic CUDA runtime and cuBLAS, consider it available
        if has_cudart and has_cublas:
            return True
    except (subprocess.TimeoutExpired, Exception):
        pass
    
    # Check common CUDA toolkit installation paths
    cuda_toolkit_paths = [
        '/usr/local/cuda/lib64',
        '/usr/local/cuda/lib',
        '/opt/cuda/lib64',
        '/opt/cuda/lib'
    ]
    
    for cuda_dir in cuda_toolkit_paths:
        if os.path.exists(cuda_dir):
            try:
                files = os.listdir(cuda_dir)
                has_cudart = any('libcudart.so' in f for f in files)
                has_cublas = any('libcublas.so' in f for f in files)

                if has_cudart and has_cublas:
                    return True
            except (PermissionError, OSError):
                pass
    
    # Check standard library paths (for distro-packaged CUDA)
    system_lib_paths = [
        '/usr/lib/x86_64-linux-gnu',
        '/usr/lib64',
        '/usr/lib'
    ]
    
    for lib_dir in system_lib_paths:
        if os.path.exists(lib_dir):
            try:
                files = os.listdir(lib_dir)
                has_cudart = any('libcudart.so' in f for f in files)
                if has_cudart:
                    return True
            except (PermissionError, OSError):
                pass
    
    return False

def get_appdir_cuda_path():
    """Get the path where CUDA libraries should be stored."""
    return os.path.expanduser("~/.local/share/TalkType/cuda")

def is_first_run():
    """Check if this is the first time the app is run."""
    flag_file = os.path.expanduser("~/.local/share/TalkType/.first_run_done")
    return not os.path.exists(flag_file)

def mark_first_run_complete():
    """Mark that the first run has been completed."""
    flag_file = os.path.expanduser("~/.local/share/TalkType/.first_run_done")
    os.makedirs(os.path.dirname(flag_file), exist_ok=True)
    with open(flag_file, 'w') as f:
        f.write('done')

def download_cuda_libraries(progress_callback=None):
    """
    Download CUDA libraries for GPU acceleration.
    Downloads wheels directly from PyPI and extracts them.
    
    Args:
        progress_callback: Optional function(message, percent) for progress updates
    
    Returns:
        bool: True if successful, False otherwise
    """
    import urllib.request
    import zipfile
    import shutil
    
    cuda_path = get_appdir_cuda_path()
    lib_path = os.path.join(cuda_path, "lib")
    
    # Create directories
    os.makedirs(lib_path, exist_ok=True)
    
    # Use pip to download packages instead of direct URLs
    cuda_packages = ['nvidia-cuda-runtime-cu12', 'nvidia-cublas-cu12', 'nvidia-cudnn-cu12']
    
    try:
        import tempfile
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Use pip to download packages
            for pkg_idx, pkg_name in enumerate(cuda_packages):
                if progress_callback:
                    percent = int((pkg_idx / len(cuda_packages)) * 70)
                    progress_callback(f"Downloading {pkg_name}...", percent)
                
                logger.info(f"📥 Downloading {pkg_name}...")
                
                try:
                    # Get the latest version from PyPI API and download directly
                    import json
                    import urllib.request
                    
                    # Get package info from PyPI
                    api_url = f"https://pypi.org/pypi/{pkg_name}/json"
                    with urllib.request.urlopen(api_url) as response:
                        data = json.loads(response.read())
                    
                    # Find the wheel file for linux x86_64
                    wheel_url = None
                    for file_info in data['urls']:
                        if (file_info['packagetype'] == 'bdist_wheel' and 
                            'x86_64' in file_info['filename'] and
                            'manylinux' in file_info['filename']):
                            wheel_url = file_info['url']
                            break
                    
                    if not wheel_url:
                        logger.error(f"No suitable wheel found for {pkg_name}")
                        return False
                    
                    # Download the wheel with progress updates
                    wheel_filename = wheel_url.split('/')[-1]
                    wheel_path = os.path.join(temp_dir, wheel_filename)
                    
                    def download_progress_hook(block_num, block_size, total_size):
                        if progress_callback and total_size > 0:
                            downloaded = block_num * block_size
                            download_percent = min(100, (downloaded / total_size) * 100)
                            # Map to overall progress: each package gets ~23% of total progress
                            base_percent = pkg_idx * 23
                            current_percent = base_percent + int((download_percent / 100) * 23)
                            progress_callback(f"Downloading {pkg_name}... {int(download_percent)}%", current_percent)
                    
                    urllib.request.urlretrieve(wheel_url, wheel_path, reporthook=download_progress_hook)
                    logger.info(f"✅ Downloaded {wheel_filename}")
                        
                except Exception as e:
                    logger.error(f"Failed to download {pkg_name}: {e}")
                    return False
            
            if progress_callback:
                progress_callback("Extracting CUDA libraries...", 70)
            
            # Extract .so files from wheels
            wheel_files = [f for f in os.listdir(temp_dir) if f.endswith('.whl')]
            
            for i, wheel_file in enumerate(wheel_files):
                wheel_path = os.path.join(temp_dir, wheel_file)
                logger.info(f"📦 Extracting {wheel_file}...")
                
                with zipfile.ZipFile(wheel_path, 'r') as zip_ref:
                    # Get list of .so files to extract for progress tracking
                    so_files = [member for member in zip_ref.namelist() 
                               if member.startswith('nvidia/') and '.so' in member]
                    
                    # Extract all .so files from nvidia/* directories
                    for j, member in enumerate(so_files):
                        # Get the relative path under nvidia/
                        rel_path = member[len('nvidia/'):]
                        target = os.path.join(lib_path, rel_path)
                        
                        # Create parent directories
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        
                        # Extract file
                        with zip_ref.open(member) as source:
                            with open(target, 'wb') as dest:
                                shutil.copyfileobj(source, dest)
                        
                        # Make executable if it's a .so file
                        if target.endswith('.so') or '.so.' in target:
                            try:
                                os.chmod(target, 0o755)
                            except (PermissionError, OSError):
                                pass
                        
                        # Update progress more frequently during extraction
                        if progress_callback and len(so_files) > 0:
                            file_progress = (j + 1) / len(so_files)
                            wheel_progress = (i + file_progress) / len(wheel_files)
                            percent = 70 + int(wheel_progress * 25)  # 70-95% for extraction
                            progress_callback(f"Extracting {wheel_file}... ({j+1}/{len(so_files)} files)", percent)
                
                if progress_callback:
                    percent = 70 + int((i + 1) / len(wheel_files) * 25)
                    progress_callback(f"Extracted {wheel_file} ({i+1}/{len(wheel_files)})", percent)
        
        if progress_callback:
            progress_callback("CUDA libraries installed successfully!", 100)
        
        logger.info(f"✅ CUDA libraries installed to {cuda_path}")
        logger.info(f"📂 Libraries extracted to {lib_path}")
        
        # List what was installed
        so_files = []
        for root, dirs, files in os.walk(lib_path):
            for f in files:
                if '.so' in f:
                    so_files.append(f)
        
        logger.info(f"✅ Installed {len(so_files)} library files")
        return True
        
    except Exception as e:
        logger.error(f"Error downloading CUDA libraries: {e}", exc_info=True)
        return False

def show_cuda_progress_dialog():
    """Show GTK progress dialog for CUDA download."""
    try:
        dialog = Gtk.Dialog(title="Downloading CUDA Libraries")
        dialog.set_default_size(500, 200)
        dialog.set_modal(True)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        dialog.set_deletable(False)  # Prevent closing during download
        
        content = dialog.get_content_area()
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        content.set_margin_start(20)
        content.set_margin_end(20)
        
        # Header
        header = Gtk.Label()
        header.set_markup('<span size="large"><b>🚀 Downloading GPU Acceleration Libraries</b></span>')
        header.set_margin_bottom(15)
        content.pack_start(header, False, False, 0)
        
        # Status label
        status_label = Gtk.Label(label="Preparing download...")
        status_label.set_margin_bottom(10)
        content.pack_start(status_label, False, False, 0)
        
        # Progress bar
        progress_bar = Gtk.ProgressBar()
        progress_bar.set_margin_bottom(15)
        progress_bar.set_show_text(True)
        content.pack_start(progress_bar, False, False, 0)
        
        # Cancel button
        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.CANCEL))
        dialog.add_action_widget(cancel_button, Gtk.ResponseType.CANCEL)
        
        dialog.show_all()
        
        # Return references to update during download
        return dialog, status_label, progress_bar
        
    except Exception as e:
        logger.error(f"Error creating progress dialog: {e}")
        return None, None, None

def show_cuda_welcome_dialog():
    """Show GTK welcome dialog for CUDA setup."""
    try:
        dialog = Gtk.Dialog(title="Welcome to TalkType!")
        dialog.set_default_size(600, 450)
        dialog.set_modal(True)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        
        # Dark theme
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-application-prefer-dark-theme", True)
    
        content = dialog.get_content_area()
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        content.set_margin_start(20)
        content.set_margin_end(20)
        
        # Header with emoji
        header = Gtk.Label()
        header.set_markup('<span size="x-large">🎮 <b>NVIDIA GPU Detected!</b></span>')
        header.set_margin_bottom(15)
        content.pack_start(header, False, False, 0)
        
        # Main message
        msg = Gtk.Label()
        msg.set_markup('Your system has an NVIDIA graphics card that can significantly accelerate TalkType speech recognition.')
        msg.set_line_wrap(True)
        msg.set_max_width_chars(60)
        msg.set_margin_bottom(15)
        content.pack_start(msg, False, False, 0)
        
        # Benefits box
        benefits_frame = Gtk.Frame()
        benefits_frame.set_label("🚀 GPU Acceleration Benefits")
        benefits_frame.set_margin_bottom(15)
        
        benefits_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        benefits_box.set_margin_top(10)
        benefits_box.set_margin_bottom(10)
        benefits_box.set_margin_start(15)
        benefits_box.set_margin_end(15)
        
        benefits = [
            "⚡ 3-5x faster transcription speed",
            "🎯 Better accuracy for longer recordings",
            "⏱️ Real-time processing for live dictation",
            "💻 Lower CPU usage during transcription"
        ]
        
        for benefit in benefits:
            label = Gtk.Label(label=benefit, xalign=0)
            benefits_box.pack_start(label, False, False, 0)
        
        benefits_frame.add(benefits_box)
        content.pack_start(benefits_frame, False, False, 0)
        
        # Setup info
        setup_label = Gtk.Label()
        setup_label.set_markup('<b>📦 One-time setup:</b> ~800MB download\nLibraries will be stored in ~/.local/share/TalkType/')
        setup_label.set_line_wrap(True)
        setup_label.set_margin_bottom(15)
        content.pack_start(setup_label, False, False, 0)
        
        # Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.CENTER)
        
        skip_button = Gtk.Button(label="Skip for Now")
        skip_button.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.CANCEL))
        button_box.pack_start(skip_button, False, False, 0)
        
        enable_button = Gtk.Button(label="🚀 Enable GPU Acceleration")
        enable_button.get_style_context().add_class("suggested-action")
        enable_button.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))
        button_box.pack_start(enable_button, False, False, 0)
        
        content.pack_start(button_box, False, False, 0)
    
        dialog.show_all()
        response = dialog.run()
        dialog.destroy()

        result = response == Gtk.ResponseType.OK
        return result
    except Exception as e:
        logger.error(f"Error in CUDA dialog: {e}", exc_info=True)
        return False

def show_initial_help_dialog():
    """Show initial help dialog for first-time users who skip CUDA download."""
    try:
        dialog = Gtk.Dialog(title="Welcome to TalkType")
        dialog.set_default_size(520, 320)
        dialog.set_resizable(False)
        dialog.set_modal(True)
        dialog.set_position(Gtk.WindowPosition.CENTER)

        content = dialog.get_content_area()
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        content.set_margin_start(25)
        content.set_margin_end(25)
        content.set_spacing(15)

        # Main instructions
        instructions = Gtk.Label()
        instructions.set_markup('''<span size="large"><b>🎙️ Welcome to TalkType!</b></span>

<b>🚀 Next Steps:</b>

<b>1. Verify Your Hotkeys</b>
   After clicking "Got It!", you'll test your hotkeys (F8 and F9)
   to ensure they work and don't conflict with other apps.

<b>2. Start Dictating!</b>
   Once verified, the service starts automatically.
   Press <b>F8</b> (push-to-talk) or <b>F9</b> (toggle mode) to dictate.

<b>✨ Key Features:</b>
• Auto-punctuation, smart quotes, 50+ languages
• GPU acceleration available (3-5x faster with NVIDIA GPU)
• Auto-timeout after 5 minutes to save system resources

<b>🎮 GPU Acceleration:</b>
Enable later for faster transcription:
Right-click tray → "Preferences" → "Advanced" tab

<b>📚 Need Help?</b>
Right-click the tray icon → "Help..." for full documentation''')
        instructions.set_line_wrap(True)
        instructions.set_xalign(0)
        instructions.set_yalign(0)
        content.pack_start(instructions, True, True, 0)

        # Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.set_margin_top(10)

        ok_btn = Gtk.Button(label="Got It!")
        ok_btn.get_style_context().add_class("suggested-action")
        ok_btn.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))
        button_box.pack_start(ok_btn, False, False, 0)

        content.pack_start(button_box, False, False, 0)

        dialog.show_all()
        dialog.run()
        dialog.destroy()

    except Exception as e:
        logger.error(f"Error showing initial help dialog: {e}", exc_info=True)

def offer_cuda_download_cli():
    """CLI fallback for CUDA download offer."""
    print("\n" + "="*60)
    print("🎮 NVIDIA GPU DETECTED!")
    print("="*60)
    print("\nYour system has an NVIDIA graphics card that can significantly")
    print("accelerate TalkType speech recognition.")
    print("\n🚀 GPU Acceleration Benefits:")
    print("  ⚡ 3-5x faster transcription speed")
    print("  🎯 Better accuracy for longer recordings")
    print("  ⏱️ Real-time processing for live dictation")
    print("  💻 Lower CPU usage during transcription")
    print("\n📦 One-time setup: ~800MB download")
    print("Libraries will be stored in ~/.local/share/TalkType/")
    print("="*60)
    
    try:
        response = input("\nWould you like to download CUDA libraries now? (y/n): ")
        return response.lower().startswith('y')
    except (EOFError, KeyboardInterrupt):
        print("\nSkipping CUDA setup")
        return False

def offer_cuda_download(show_gui=True):
    """
    Smart CUDA download offer based on context:
    - First run + GPU detected + no CUDA: Show welcome dialog
    - Subsequent runs: Don't show (can be triggered from preferences)
    """
    # Only offer on first run
    if not is_first_run():
        return False
    
    # Check if GPU is present
    if not detect_nvidia_gpu():
        # Don't mark first run complete - hotkey verification still needed
        return False

    # Check if CUDA is already installed
    if has_cuda_libraries():
        # Don't mark first run complete - hotkey verification still needed
        return False
    
    # Offer CUDA download
    logger.info("🎮 NVIDIA GPU detected!")

    if show_gui:
        try:
            logger.debug("Showing CUDA welcome dialog...")
            wants_cuda = show_cuda_welcome_dialog()
            logger.debug(f"Dialog returned: {wants_cuda}")
            if wants_cuda:
                logger.info("User chose to download CUDA...")
                
                # Show progress dialog
                progress_dialog, status_label, progress_bar = show_cuda_progress_dialog()
                if not progress_dialog:
                    # Fallback to background download if progress dialog fails
                    import threading
                    def background_download():
                        success = download_cuda_libraries()
                        # Don't mark first run complete - hotkey verification still needed
                    download_thread = threading.Thread(target=background_download)
                    download_thread.daemon = True
                    download_thread.start()
                    return True
                
                # Download with progress updates
                import threading
                from gi.repository import GLib

                def progress_callback(message, percent):
                    """
                    Thread-safe progress callback for background download.
                    Uses GLib.idle_add() to schedule UI updates on main GTK thread.
                    """
                    def update_ui():
                        status_label.set_text(message)
                        progress_bar.set_fraction(percent / 100.0)
                        progress_bar.set_text(f"{percent}%")
                        return False  # Don't repeat
                    GLib.idle_add(update_ui)
                
                def background_download_with_progress():
                    """
                    Background thread function for CUDA library download.
                    All UI updates use GLib.idle_add() for thread safety.
                    """
                    try:
                        success = download_cuda_libraries(progress_callback)
                        def finish_ui():
                            if success:
                                status_label.set_text("✅ Download completed successfully!")
                                progress_bar.set_fraction(1.0)
                                progress_bar.set_text("100%")

                                # Auto-enable GPU mode in config after successful download
                                try:
                                    from . import config
                                    s = config.load_config()
                                    if s.device != "cuda":
                                        s.device = "cuda"
                                        config.save_config(s)
                                        logger.info("✅ Automatically enabled CUDA in config")
                                except Exception as e:
                                    logger.warning(f"Could not auto-enable CUDA in config: {e}")

                                # Close progress dialog after delay and show success dialog
                                # Runs on main GTK thread via GLib.timeout_add()
                                def show_success_dialog():
                                    progress_dialog.destroy()
                                    
                                    # Show success dialog with instructions
                                    success_dialog = Gtk.Dialog(title="🎉 GPU Acceleration Ready!")
                                    success_dialog.set_default_size(500, 300)
                                    success_dialog.set_modal(True)
                                    success_dialog.set_position(Gtk.WindowPosition.CENTER)
                                    
                                    content = success_dialog.get_content_area()
                                    content.set_margin_top(20)
                                    content.set_margin_bottom(20)
                                    content.set_margin_start(20)
                                    content.set_margin_end(20)
                                    
                                    # Success message
                                    header = Gtk.Label()
                                    header.set_markup('<span size="large"><b>🚀 CUDA Libraries Installed Successfully!</b></span>')
                                    header.set_margin_bottom(15)
                                    content.pack_start(header, False, False, 0)
                                    
                                    # Instructions
                                    instructions = Gtk.Label()
                                    instructions.set_markup('''<b>✨ CUDA Libraries Installed!</b>

<b>🚀 Next Steps:</b>

<b>1. Verify Your Hotkeys</b>
   After clicking "Got It!", you'll test your hotkeys (F8 and F9)
   to ensure they work and don't conflict with other apps.

<b>2. Start Dictating!</b>
   Once verified, the service starts automatically with GPU acceleration!
   Press <b>F8</b> (push-to-talk) or <b>F9</b> (toggle mode) to dictate.

<b>💡 GPU Benefits:</b>
• 3-5x faster transcription than CPU mode
• Smoother performance with larger AI models
• Lower CPU usage during dictation

<b>💡 Power Management:</b>
The service automatically pauses after 5 minutes of inactivity.
Adjust this in Preferences → Advanced.

<b>📚 Need Help?</b>
Right-click the tray icon → "Help..." for full documentation''')
                                    instructions.set_line_wrap(True)
                                    instructions.set_xalign(0)
                                    content.pack_start(instructions, True, True, 0)

                                    # Add some space before buttons
                                    spacer = Gtk.Label()
                                    spacer.set_margin_top(10)
                                    content.pack_start(spacer, False, False, 0)

                                    # Buttons
                                    ok_btn = Gtk.Button(label="Got It!")
                                    ok_btn.get_style_context().add_class("suggested-action")
                                    ok_btn.connect("clicked", lambda w: success_dialog.response(Gtk.ResponseType.OK))
                                    success_dialog.add_action_widget(ok_btn, Gtk.ResponseType.OK)

                                    success_dialog.show_all()
                                    success_dialog.run()
                                    success_dialog.destroy()
                                    
                                    return False
                                GLib.timeout_add(SUCCESS_DIALOG_DELAY_MS, show_success_dialog)
                            else:
                                status_label.set_text("❌ Download failed")
                                # Close dialog after 2 seconds
                                def close_dialog():
                                    progress_dialog.response(Gtk.ResponseType.OK)
                                    return False
                                GLib.timeout_add(ERROR_DIALOG_DELAY_MS, close_dialog)
                            return False
                        # Schedule UI update on main GTK thread
                        GLib.idle_add(finish_ui)
                        # Don't mark first run complete - hotkey verification still needed
                    except Exception as e:
                        def error_ui():
                            status_label.set_text(f"❌ Error: {e}")
                            return False
                        # Schedule error UI update on main GTK thread
                        GLib.idle_add(error_ui)
                
                download_thread = threading.Thread(target=background_download_with_progress)
                download_thread.daemon = True
                download_thread.start()
                
                # Show progress dialog (blocks until download completes)
                progress_dialog.run()
                progress_dialog.destroy()
                return True
            else:
                logger.info("User skipped CUDA download")
                # Show initial help dialog for first-time users who skip CUDA
                show_initial_help_dialog()
                # Don't mark first run complete yet - wait for hotkey verification in app.py
                return False
        except Exception as e:
            logger.error(f"Failed to show GUI dialog: {e}", exc_info=True)
            # Fall back to CLI
    
    wants_cuda = offer_cuda_download_cli()

    if wants_cuda:
        success = download_cuda_libraries()
        # Don't mark first run complete - hotkey verification still needed
        return success
    else:
        # Don't mark first run complete - hotkey verification still needed
        return False

if __name__ == "__main__":
    # Test the module
    print("Testing CUDA Helper Module")
    print("="*40)
    print(f"NVIDIA GPU detected: {detect_nvidia_gpu()}")
    print(f"CUDA libraries present: {has_cuda_libraries()}")
    print(f"CUDA path: {get_appdir_cuda_path()}")
    print(f"First run: {is_first_run()}")


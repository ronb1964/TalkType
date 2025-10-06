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

def detect_nvidia_gpu():
    """Check if NVIDIA GPU is present using nvidia-smi."""
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
                              capture_output=True, text=True, timeout=5)
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
                                      capture_output=True, text=True, timeout=2)
                if not result.stdout.strip():
                    found_all = False
                    break
            except:
                found_all = False
                break
        
        if found_all:
            return True
    
    # Check system-wide CUDA installation via ldconfig (most reliable)
    try:
        result = subprocess.run(['ldconfig', '-p'], capture_output=True, text=True, timeout=2)
        has_cudart = 'libcudart.so' in result.stdout
        has_cublas = 'libcublas.so' in result.stdout
        has_cudnn = 'libcudnn.so' in result.stdout
        
        # If we have basic CUDA runtime and cuBLAS, consider it available
        if has_cudart and has_cublas:
            return True
    except:
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
            except:
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
            except:
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
                
                print(f"📥 Downloading {pkg_name}...")
                
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
                        print(f"❌ No suitable wheel found for {pkg_name}")
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
                    print(f"✅ Downloaded {wheel_filename}")
                        
                except Exception as e:
                    print(f"❌ Failed to download {pkg_name}: {e}")
                    return False
            
            if progress_callback:
                progress_callback("Extracting CUDA libraries...", 70)
            
            # Extract .so files from wheels
            wheel_files = [f for f in os.listdir(temp_dir) if f.endswith('.whl')]
            
            for i, wheel_file in enumerate(wheel_files):
                wheel_path = os.path.join(temp_dir, wheel_file)
                print(f"📦 Extracting {wheel_file}...")
                
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
                            except:
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
        
        print(f"✅ CUDA libraries installed to {cuda_path}")
        print(f"📂 Libraries extracted to {lib_path}")
        
        # List what was installed
        so_files = []
        for root, dirs, files in os.walk(lib_path):
            for f in files:
                if '.so' in f:
                    so_files.append(f)
        
        print(f"✅ Installed {len(so_files)} library files")
        return True
        
    except Exception as e:
        print(f"❌ Error downloading CUDA libraries: {e}")
        import traceback
        traceback.print_exc()
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
        print(f"Error creating progress dialog: {e}")
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
        
        print(f"DEBUG: Dialog response = {response}")
        print(f"DEBUG: Gtk.ResponseType.OK = {Gtk.ResponseType.OK}")
        result = response == Gtk.ResponseType.OK
        print(f"DEBUG: Returning {result}")
        return result
    except Exception as e:
        print(f"Error in CUDA dialog: {e}")
        import traceback
        traceback.print_exc()
        return False

def show_initial_help_dialog():
    """Show initial help dialog for first-time users who skip CUDA download."""
    try:
        dialog = Gtk.Dialog(title="🎙️ Welcome to TalkType!")
        dialog.set_default_size(480, 280)
        dialog.set_size_request(480, 280)  # Force the size
        dialog.set_resizable(False)  # Prevent resizing
        dialog.set_modal(True)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        
        content = dialog.get_content_area()
        content.set_margin_top(5)
        content.set_margin_bottom(5)
        content.set_margin_start(8)
        content.set_margin_end(8)
        content.set_spacing(5)  # Reduce spacing between elements
        
        # Header
        header = Gtk.Label()
        header.set_markup('<span size="large"><b>🎙️ Welcome to TalkType!</b></span>')
        header.set_margin_bottom(3)
        content.pack_start(header, False, False, 0)
        
        # Instructions
        instructions = Gtk.Label()
        instructions.set_markup('''<b>Getting Started:</b>

1. <b>Start the Service:</b> Right-click the tray icon → "Start Service"
2. <b>Begin Dictating:</b> Press F8 (push-to-talk) or F9 (toggle mode)
   • Red microphone icon appears during recording
3. <b>Configure Settings:</b> Right-click → "Preferences" to customize

<b>💡 Key Features:</b>
• <b>Dual Hotkey Modes:</b> F8 (hold to talk) or F9 (toggle on/off)
• <b>Smart Text Processing:</b> Auto-punctuation, smart quotes, spacing
• <b>Language Support:</b> Auto-detect or manually select language
• <b>Power Management:</b> Auto-timeout to save battery when idle

<b>🎮 GPU Acceleration:</b>
You can enable GPU acceleration later for 3-5x faster transcription:
• Right-click tray → "Preferences" → "Advanced" tab
• Or use the "Download CUDA Libraries" menu option

<b>📚 Need Help?</b>
Right-click the tray icon → "Help..." for comprehensive feature guide''')
        instructions.set_line_wrap(True)
        instructions.set_xalign(0)
        content.pack_start(instructions, True, True, 0)
        
        # Add some space before buttons
        spacer = Gtk.Label()
        spacer.set_margin_top(10)
        content.pack_start(spacer, False, False, 0)
        
        # Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.CENTER)
        
        start_service_btn = Gtk.Button(label="🚀 Start Service Now")
        start_service_btn.get_style_context().add_class("suggested-action")
        start_service_btn.connect("clicked", lambda w: dialog.response(1))
        button_box.pack_start(start_service_btn, False, False, 0)
        
        ok_btn = Gtk.Button(label="Got It!")
        ok_btn.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))
        button_box.pack_start(ok_btn, False, False, 0)
        
        content.pack_start(button_box, False, False, 0)
        
        dialog.show_all()
        response = dialog.run()
        dialog.destroy()
        
        # If user clicked "Start Service Now", try to start it
        if response == 1:
            try:
                import subprocess
                import os
                
                # Find the dictate script relative to this module
                current_dir = os.path.dirname(__file__)  # usr/src/talktype
                usr_dir = os.path.dirname(os.path.dirname(current_dir))  # usr
                dictate_script = os.path.join(usr_dir, "bin", "dictate")
                
                if os.path.exists(dictate_script):
                    # Stop any existing service first
                    subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
                    # Start the service using the dictate script
                    subprocess.Popen([dictate_script], env=os.environ.copy())
                    print(f"Started dictation service via {dictate_script}")
                else:
                    # Fallback: use sys.executable (bundled Python)
                    subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
                    subprocess.Popen([sys.executable, "-m", "talktype.app"], env=os.environ.copy())
                    print("Started dictation service via Python module")
            except Exception as e:
                print(f"Failed to start service from help dialog: {e}")
        
    except Exception as e:
        print(f"Error showing initial help dialog: {e}")
        import traceback
        traceback.print_exc()

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
        mark_first_run_complete()
        return False
    
    # Check if CUDA is already installed
    if has_cuda_libraries():
        mark_first_run_complete()
        return False
    
    # Offer CUDA download
    print("🎮 NVIDIA GPU detected!")
    
    if show_gui:
        try:
            print("Showing CUDA welcome dialog...")
            wants_cuda = show_cuda_welcome_dialog()
            print(f"Dialog returned: {wants_cuda}")
            if wants_cuda:
                print("User chose to download CUDA...")
                
                # Show progress dialog
                progress_dialog, status_label, progress_bar = show_cuda_progress_dialog()
                if not progress_dialog:
                    # Fallback to background download if progress dialog fails
                    import threading
                    def background_download():
                        success = download_cuda_libraries()
                        mark_first_run_complete()
                    download_thread = threading.Thread(target=background_download)
                    download_thread.daemon = True
                    download_thread.start()
                    return True
                
                # Download with progress updates
                import threading
                from gi.repository import GLib
                
                def progress_callback(message, percent):
                    def update_ui():
                        status_label.set_text(message)
                        progress_bar.set_fraction(percent / 100.0)
                        progress_bar.set_text(f"{percent}%")
                        return False
                    GLib.idle_add(update_ui)
                
                def background_download_with_progress():
                    try:
                        success = download_cuda_libraries(progress_callback)
                        def finish_ui():
                            if success:
                                status_label.set_text("✅ Download completed successfully!")
                                progress_bar.set_fraction(1.0)
                                progress_bar.set_text("100%")
                                
                                # Close progress dialog after 1 second and show success dialog
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
                                    instructions.set_markup('''<b>Next Steps:</b>

1. <b>Start the Service:</b> Right-click the tray icon → "Start Service"
2. <b>Begin Dictating:</b> Press F8 (push-to-talk) or F9 (toggle mode) - red mic icon shows when recording
3. <b>GPU Mode:</b> CUDA (GPU) is now available in Preferences → General

<b>💡 Tips:</b>
• GPU acceleration is 3-5x faster than CPU mode
• The service must be started manually to begin dictation
• Right-click the tray icon → "Help..." for comprehensive feature guide''')
                                    instructions.set_line_wrap(True)
                                    instructions.set_xalign(0)
                                    content.pack_start(instructions, True, True, 0)
                                    
                                    # Add some space before buttons
                                    spacer = Gtk.Label()
                                    spacer.set_margin_top(10)
                                    content.pack_start(spacer, False, False, 0)
                                    
                                    # Buttons
                                    start_service_btn = Gtk.Button(label="🚀 Start Service Now")
                                    start_service_btn.connect("clicked", lambda w: success_dialog.response(1))
                                    success_dialog.add_action_widget(start_service_btn, 1)
                                    
                                    ok_btn = Gtk.Button(label="OK")
                                    ok_btn.connect("clicked", lambda w: success_dialog.response(Gtk.ResponseType.OK))
                                    success_dialog.add_action_widget(ok_btn, Gtk.ResponseType.OK)
                                    
                                    success_dialog.show_all()
                                    response = success_dialog.run()
                                    success_dialog.destroy()
                                    
                                    # If user clicked "Start Service Now", try to start it
                                    if response == 1:
                                        try:
                                            import subprocess
                                            import os
                                            
                                            # Find the dictate script relative to this module
                                            # We're in usr/src/talktype/cuda_helper.py
                                            # dictate is in usr/bin/dictate
                                            current_dir = os.path.dirname(__file__)  # usr/src/talktype
                                            usr_dir = os.path.dirname(os.path.dirname(current_dir))  # usr
                                            dictate_script = os.path.join(usr_dir, "bin", "dictate")
                                            
                                            if os.path.exists(dictate_script):
                                                # Stop any existing service first
                                                subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
                                                # Start the service using the dictate script
                                                subprocess.Popen([dictate_script], env=os.environ.copy())
                                                print(f"Started dictation service via {dictate_script}")
                                            else:
                                                # Fallback: use sys.executable (bundled Python)
                                                subprocess.run(["pkill", "-f", "talktype.app"], capture_output=True)
                                                subprocess.Popen([sys.executable, "-m", "talktype.app"], env=os.environ.copy())
                                                print("Started dictation service via Python module")
                                        except Exception as e:
                                            print(f"Failed to start service from success dialog: {e}")
                                            pass  # Service start will be handled by tray
                                    
                                    return False
                                GLib.timeout_add(1000, show_success_dialog)
                            else:
                                status_label.set_text("❌ Download failed")
                                # Close dialog after 2 seconds
                                def close_dialog():
                                    progress_dialog.response(Gtk.ResponseType.OK)
                                    return False
                                GLib.timeout_add(2000, close_dialog)
                            return False
                        GLib.idle_add(finish_ui)
                        mark_first_run_complete()
                    except Exception as e:
                        def error_ui():
                            status_label.set_text(f"❌ Error: {e}")
                            return False
                        GLib.idle_add(error_ui)
                
                download_thread = threading.Thread(target=background_download_with_progress)
                download_thread.daemon = True
                download_thread.start()
                
                # Show progress dialog (blocks until download completes)
                progress_dialog.run()
                progress_dialog.destroy()
                return True
            else:
                print("User skipped CUDA download")
                # Show initial help dialog for first-time users who skip CUDA
                show_initial_help_dialog()
                mark_first_run_complete()
                return False
        except Exception as e:
            print(f"Failed to show GUI dialog: {e}")
            import traceback
            traceback.print_exc()
            # Fall back to CLI
    
    wants_cuda = offer_cuda_download_cli()
    
    if wants_cuda:
        success = download_cuda_libraries()
        mark_first_run_complete()
        return success
    else:
        mark_first_run_complete()
        return False

if __name__ == "__main__":
    # Test the module
    print("Testing CUDA Helper Module")
    print("="*40)
    print(f"NVIDIA GPU detected: {detect_nvidia_gpu()}")
    print(f"CUDA libraries present: {has_cuda_libraries()}")
    print(f"CUDA path: {get_appdir_cuda_path()}")
    print(f"First run: {is_first_run()}")


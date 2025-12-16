"""
Model Download Helper for TalkType
Handles WhisperModel downloads with progress UI
"""
import os

# CRITICAL: Disable XET downloads BEFORE huggingface_hub is imported anywhere
# XET bypasses tqdm_class progress tracking, breaking our progress UI
os.environ["HF_HUB_DISABLE_XET"] = "1"

import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from .logger import setup_logger

logger = setup_logger(__name__)

# Model repository names on HuggingFace
MODEL_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
}

# Model sizes for display (compressed size users will download)
MODEL_DISPLAY_SIZES = {
    "tiny": "39 MB",
    "base": "74 MB",
    "small": "244 MB",
    "medium": "769 MB",
    "large-v3": "~3 GB"
}


def is_model_cached(model_name):
    """
    Check if a Whisper model is already downloaded/cached.

    Args:
        model_name: Model size (e.g., "tiny", "small", "medium", "large-v3")

    Returns:
        bool: True if model is cached, False otherwise
    """
    try:
        from faster_whisper import WhisperModel
        # Try to load with local_files_only=True
        # This will succeed if model is cached, fail if not
        model = WhisperModel(
            model_name,
            device="cpu",
            local_files_only=True
        )
        del model  # Clean up
        return True
    except Exception:
        return False


def download_model_with_progress(model_name, device="cpu", compute_type="int8", parent=None, show_confirmation=True):
    """
    Download a Whisper model with progress dialog.

    Args:
        model_name: Model size (e.g., "tiny", "small", "medium", "large-v3")
        device: Device to use ("cpu" or "cuda")
        compute_type: Compute type ("int8", "float16", etc.)
        parent: Optional parent window for dialog
        show_confirmation: Whether to show confirmation dialog before download (default True)

    Returns:
        WhisperModel instance or None if cancelled/failed
    """
    from faster_whisper import WhisperModel

    # Check if already cached
    if is_model_cached(model_name):
        logger.info(f"Model {model_name} already cached, loading directly")
        return WhisperModel(model_name, device=device, compute_type=compute_type)

    size_str = MODEL_DISPLAY_SIZES.get(model_name, "unknown size")

    # Show confirmation dialog before starting download
    if show_confirmation:
        confirm_dialog = Gtk.MessageDialog(
            parent=parent,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=f"Download {model_name.title()} Model?"
        )

        # Apply dark theme to dialog
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-application-prefer-dark-theme", True)

        confirm_dialog.format_secondary_text(
            f"TalkType needs to download the {model_name} AI model ({size_str}) for speech recognition.\n\n"
            f"This is a one-time download that will be cached for future use.\n\n"
            "Continue with download?"
        )
        confirm_dialog.set_position(Gtk.WindowPosition.CENTER)
        response = confirm_dialog.run()
        confirm_dialog.destroy()

        if response != Gtk.ResponseType.OK:
            logger.info(f"User declined model download: {model_name}")
            return None

    # Show progress dialog with dark theme
    progress_dialog = Gtk.Dialog(title=f"Downloading Model: {model_name}")
    progress_dialog.set_default_size(500, 150)
    progress_dialog.set_modal(True)
    progress_dialog.set_position(Gtk.WindowPosition.CENTER)

    # Apply dark theme to dialog
    settings = Gtk.Settings.get_default()
    if settings:
        settings.set_property("gtk-application-prefer-dark-theme", True)

    if parent:
        progress_dialog.set_transient_for(parent)

    content = progress_dialog.get_content_area()
    content.set_margin_top(20)
    content.set_margin_bottom(20)
    content.set_margin_start(30)
    content.set_margin_end(30)
    content.set_spacing(15)

    # Title
    title_label = Gtk.Label()
    title_label.set_markup(f'<span size="large"><b>Downloading {model_name} Model</b></span>')
    content.pack_start(title_label, False, False, 0)

    # Status label
    status_label = Gtk.Label()
    status_label.set_markup(f'<span>Downloading from Hugging Face... ({size_str})</span>')
    status_label.set_line_wrap(True)
    content.pack_start(status_label, False, False, 0)

    # Progress bar with percentage text
    progress_bar = Gtk.ProgressBar()
    progress_bar.set_show_text(True)
    progress_bar.set_text("0%")
    content.pack_start(progress_bar, False, False, 0)

    # Info label
    info_label = Gtk.Label()
    info_label.set_markup('<span size="small"><i>This may take several minutes on first download...</i></span>')
    info_label.set_opacity(0.7)
    content.pack_start(info_label, False, False, 0)

    # Add Cancel button to action area
    cancel_button = Gtk.Button(label="Cancel")
    cancel_button.set_can_default(True)
    cancel_button.show()  # Explicitly show the button
    progress_dialog.add_action_widget(cancel_button, Gtk.ResponseType.CANCEL)

    # Show all widgets
    progress_dialog.show_all()

    # Download state
    cancel_event = threading.Event()
    download_result = [None]
    download_error = [None]
    download_done = [False]

    # Progress tracking state (shared between threads)
    progress_state = {
        'total_bytes': 0,
        'downloaded_bytes': 0,
        'current_file': '',
        'last_percent': -1
    }

    def update_ui_progress(percent, file_info=""):
        """Update progress bar from main thread"""
        # Only update if percent changed (reduces UI updates)
        if int(percent) == progress_state['last_percent']:
            return
        progress_state['last_percent'] = int(percent)

        def do_update():
            progress_bar.set_fraction(percent / 100.0)
            progress_bar.set_text(f"{int(percent)}%")
            if file_info:
                status_label.set_markup(f'<span>{file_info}</span>')
            return False
        GLib.idle_add(do_update)

    def do_download():
        """Download model files with byte-level progress tracking"""
        try:
            if cancel_event.is_set():
                return

            logger.info(f"Downloading model {model_name} using huggingface_hub")

            # Import huggingface_hub
            from huggingface_hub import hf_hub_download, list_repo_tree
            from huggingface_hub.utils import disable_progress_bars
            import tqdm

            # Disable huggingface_hub's console progress bars
            disable_progress_bars()

            repo_id = MODEL_REPOS.get(model_name)
            if not repo_id:
                raise ValueError(f"Unknown model: {model_name}")

            # Get list of files with sizes
            try:
                files_info = list(list_repo_tree(repo_id, recursive=True))
                # Filter to only files (not directories)
                files_with_sizes = [(f.path, f.size) for f in files_info if hasattr(f, 'size') and f.size is not None]
                total_bytes = sum(size for _, size in files_with_sizes)
                progress_state['total_bytes'] = total_bytes
                logger.info(f"Model {model_name}: {len(files_with_sizes)} files, {total_bytes / 1024 / 1024:.1f} MB total")
            except Exception as e:
                logger.warning(f"Could not get file sizes: {e}")
                files_with_sizes = []
                total_bytes = 0

            if not files_with_sizes:
                # Fallback - just load the model directly
                update_ui_progress(50, "Downloading model...")
                model = WhisperModel(
                    model_name,
                    device=device,
                    compute_type=compute_type,
                    cpu_threads=os.cpu_count() or 4
                )
                download_result[0] = model
                return

            # Create custom tqdm class that updates our progress bar
            class GtkProgressTqdm(tqdm.tqdm):
                """Custom tqdm that updates GTK progress bar"""
                def __init__(self, *args, **kwargs):
                    import io
                    # Store the file being downloaded
                    self._current_file = kwargs.get('desc', 'file')
                    # Pop 'name' kwarg that huggingface_hub passes but tqdm doesn't accept
                    kwargs.pop('name', None)
                    # CRITICAL: Force disable=False - tqdm sets disable=True when no TTY,
                    # but we're updating a GTK progress bar, not a terminal!
                    kwargs['disable'] = False
                    # Suppress console output - redirect to null device
                    kwargs['file'] = io.StringIO()
                    super().__init__(*args, **kwargs)

                def update(self, n=1):
                    if cancel_event.is_set():
                        raise InterruptedError("Download cancelled")

                    # Call parent update
                    super().update(n)

                    # Update downloaded bytes
                    progress_state['downloaded_bytes'] += n

                    # Calculate overall progress
                    if progress_state['total_bytes'] > 0:
                        percent = (progress_state['downloaded_bytes'] / progress_state['total_bytes']) * 95
                        percent = min(95, percent)  # Cap at 95% until model loads
                        update_ui_progress(percent, f"Downloading {self._current_file}...")

            # Download each file with progress tracking
            for filename, file_size in files_with_sizes:
                if cancel_event.is_set():
                    raise InterruptedError("Download cancelled")

                progress_state['current_file'] = filename
                bytes_before = progress_state['downloaded_bytes']

                try:
                    # Download with our custom tqdm class
                    hf_hub_download(
                        repo_id=repo_id,
                        filename=filename,
                        tqdm_class=GtkProgressTqdm,
                    )
                    # If no progress updates happened, file was cached - update manually
                    if progress_state['downloaded_bytes'] == bytes_before:
                        progress_state['downloaded_bytes'] += file_size
                        if progress_state['total_bytes'] > 0:
                            percent = (progress_state['downloaded_bytes'] / progress_state['total_bytes']) * 95
                            percent = min(95, percent)
                            update_ui_progress(percent, f"Loaded from cache: {filename}")
                except InterruptedError:
                    raise
                except Exception as e:
                    # Some files might already be cached or optional
                    logger.warning(f"Error downloading {filename}: {e}")
                    # Add file size to downloaded bytes anyway (might be cached)
                    progress_state['downloaded_bytes'] += file_size

            if cancel_event.is_set():
                return

            # Final progress update
            update_ui_progress(95, "Loading model...")
            logger.info(f"All files downloaded, loading model {model_name}")

            # Now load the model from cache
            model = WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
                cpu_threads=os.cpu_count() or 4
            )

            if not cancel_event.is_set():
                download_result[0] = model
                logger.info(f"Model {model_name} loaded successfully")

        except InterruptedError:
            logger.info(f"Model download interrupted by user")
        except Exception as e:
            download_error[0] = e
            logger.error(f"Model download failed: {e}")
        finally:
            download_done[0] = True

        def close_dialog():
            # Set to 100% before closing
            progress_bar.set_fraction(1.0)
            progress_bar.set_text("100%")
            # Small delay so user sees 100%
            GLib.timeout_add(200, lambda: progress_dialog.response(Gtk.ResponseType.OK) or False)
            return False
        GLib.idle_add(close_dialog)

    # Start download thread
    download_thread = threading.Thread(target=do_download)
    download_thread.daemon = True
    download_thread.start()

    # Run dialog
    response = progress_dialog.run()
    progress_dialog.destroy()

    # Check if cancelled
    if response == Gtk.ResponseType.CANCEL or response == Gtk.ResponseType.DELETE_EVENT:
        logger.info(f"User cancelled model download: {model_name}")
        cancel_event.set()
        return None

    # Wait for download to complete
    download_thread.join()

    # Check for errors
    if download_error[0]:
        msg = Gtk.MessageDialog(
            parent=parent,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Model Download Failed"
        )

        # Apply dark theme
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-application-prefer-dark-theme", True)

        msg.format_secondary_text(
            f"Could not download {model_name} model.\n\n"
            f"Error: {str(download_error[0])}\n\n"
            "Check your internet connection and try again."
        )
        msg.run()
        msg.destroy()
        return None

    return download_result[0]

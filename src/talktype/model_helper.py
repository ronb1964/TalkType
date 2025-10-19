"""
Model Download Helper for TalkType
Handles WhisperModel downloads with progress UI
"""
import os
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from .logger import setup_logger

logger = setup_logger(__name__)


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


def download_model_with_progress(model_name, device="cpu", compute_type="int8", parent=None):
    """
    Download a Whisper model with progress dialog.

    Args:
        model_name: Model size (e.g., "tiny", "small", "medium", "large-v3")
        device: Device to use ("cpu" or "cuda")
        compute_type: Compute type ("int8", "float16", etc.)
        parent: Optional parent window for dialog

    Returns:
        WhisperModel instance or None if cancelled/failed
    """
    from faster_whisper import WhisperModel

    # Check if already cached
    if is_model_cached(model_name):
        logger.info(f"Model {model_name} already cached, loading directly")
        return WhisperModel(model_name, device=device, compute_type=compute_type)

    # Show progress dialog
    progress_dialog = Gtk.Dialog(title=f"Downloading Model: {model_name}")
    progress_dialog.set_default_size(500, 150)
    progress_dialog.set_modal(True)
    progress_dialog.set_position(Gtk.WindowPosition.CENTER)

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
    model_sizes = {
        "tiny": "39 MB",
        "base": "74 MB",
        "small": "244 MB",
        "medium": "769 MB",
        "large-v3": "~3 GB"
    }
    size_str = model_sizes.get(model_name, "unknown size")
    title_label.set_markup(f'<span size="large"><b>Downloading {model_name} Model</b></span>')
    content.pack_start(title_label, False, False, 0)

    # Status label
    status_label = Gtk.Label()
    status_label.set_markup(f'<span>Downloading from Hugging Face... ({size_str})</span>')
    status_label.set_line_wrap(True)
    content.pack_start(status_label, False, False, 0)

    # Progress bar (indeterminate pulse mode since we can't track HF download progress)
    progress_bar = Gtk.ProgressBar()
    content.pack_start(progress_bar, False, False, 0)

    # Info label
    info_label = Gtk.Label()
    info_label.set_markup('<span size="small"><i>This may take several minutes on first download...</i></span>')
    info_label.set_opacity(0.7)
    content.pack_start(info_label, False, False, 0)

    # Add Cancel button
    cancel_button = Gtk.Button(label="Cancel")
    progress_dialog.add_action_widget(cancel_button, Gtk.ResponseType.CANCEL)

    progress_dialog.show_all()

    # Download state
    cancel_event = threading.Event()
    download_result = [None]
    download_error = [None]

    def pulse_progress():
        """Pulse the progress bar while downloading"""
        if not cancel_event.is_set():
            progress_bar.pulse()
            return True  # Continue pulsing
        return False  # Stop pulsing

    def do_download():
        """Download model in background thread"""
        try:
            # Periodically check for cancellation (faster-whisper doesn't support cancel)
            # We'll just load the model - if user cancels, we abandon the download
            if not cancel_event.is_set():
                model = WhisperModel(
                    model_name,
                    device=device,
                    compute_type=compute_type,
                    cpu_threads=os.cpu_count() or 4
                )
                if not cancel_event.is_set():
                    download_result[0] = model
        except Exception as e:
            download_error[0] = e
            logger.error(f"Model download failed: {e}")

        def close_dialog():
            progress_dialog.response(Gtk.ResponseType.OK)
            return False
        GLib.idle_add(close_dialog)

    # Start download thread
    download_thread = threading.Thread(target=do_download)
    download_thread.daemon = True
    download_thread.start()

    # Start progress bar pulsing
    GLib.timeout_add(100, pulse_progress)

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
        msg.format_secondary_text(
            f"Could not download {model_name} model.\n\n"
            f"Error: {str(download_error[0])}\n\n"
            "Check your internet connection and try again."
        )
        msg.run()
        msg.destroy()
        return None

    return download_result[0]

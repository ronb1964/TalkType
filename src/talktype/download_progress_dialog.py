#!/usr/bin/env python3
"""
Unified Download Progress Dialog for TalkType
Handles CUDA libraries and GNOME extension downloads with individual progress tracking
"""

import os
import threading
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib

try:
    from talktype.logger import setup_logger
    logger = setup_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class DownloadTask:
    """Represents a single download task with progress tracking."""

    def __init__(self, name, description, size_text, download_func):
        """
        Initialize a download task.

        Args:
            name: Display name (e.g., "CUDA Libraries")
            description: Short description
            size_text: Size indicator (e.g., "~800MB")
            download_func: Function that performs the download
                          Should accept (progress_callback, cancel_event) args
                          progress_callback signature: func(message, percent)
        """
        self.name = name
        self.description = description
        self.size_text = size_text
        self.download_func = download_func
        self.cancelled = False
        self.completed = False
        self.success = False
        self.cancel_event = threading.Event()


class UnifiedDownloadDialog:
    """
    Unified download progress dialog that can handle multiple downloads simultaneously.
    Each download task gets its own progress bar and cancel button.
    """

    def __init__(self, parent=None):
        """
        Initialize the unified download dialog.

        Args:
            parent: Optional parent window for the dialog
        """
        self.parent = parent
        self.tasks = []
        self.task_widgets = {}  # Maps task to its UI widgets
        self.dialog = None
        self.all_completed = False

    def add_task(self, task):
        """Add a download task to the dialog."""
        self.tasks.append(task)

    def _build_dialog(self):
        """Build the GTK dialog with progress bars for each task."""
        self.dialog = Gtk.Dialog(title="Setting up TalkType")
        self.dialog.set_default_size(600, 200 + (len(self.tasks) * 120))
        self.dialog.set_modal(True)
        self.dialog.set_position(Gtk.WindowPosition.CENTER)
        self.dialog.set_resizable(False)

        if self.parent:
            self.dialog.set_transient_for(self.parent)

        # Apply dark theme styling
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            window {
                background-color: #2b2b2b;
            }
            .task-box {
                background-color: #363636;
                border-radius: 8px;
                padding: 15px;
                margin: 8px;
            }
            .task-title {
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
            }
            .task-status {
                color: #b8b8b8;
                font-size: 12px;
            }
            progressbar {
                min-height: 20px;
            }
            progressbar progress {
                background-color: #4285f4;
                border-radius: 4px;
            }
            progressbar trough {
                background-color: #1a1a1a;
                border-radius: 4px;
            }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            self.dialog.get_screen() if self.dialog.get_screen() else Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        content = self.dialog.get_content_area()
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        content.set_margin_start(30)
        content.set_margin_end(30)
        content.set_spacing(15)

        # Main title
        title_label = Gtk.Label()
        title_label.set_markup('<span size="x-large"><b>Setting up TalkType</b></span>')
        content.pack_start(title_label, False, False, 0)

        # Description
        desc_label = Gtk.Label()
        desc_label.set_markup('<span>Downloading optional components...</span>')
        desc_label.set_opacity(0.8)
        content.pack_start(desc_label, False, False, 5)

        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(5)
        sep.set_margin_bottom(10)
        content.pack_start(sep, False, False, 0)

        # Create UI for each task
        for task in self.tasks:
            task_box = self._create_task_widget(task)
            content.pack_start(task_box, False, False, 0)

    def _create_task_widget(self, task):
        """Create UI widget for a single download task."""
        # Main container with rounded background
        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.NONE)
        frame.get_style_context().add_class('task-box')

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(5)
        vbox.set_margin_bottom(5)

        # Header row: Icon + Title + Size + Cancel button
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        # Task title
        title_label = Gtk.Label()
        title_label.set_markup(f'<b>{task.name}</b> <span size="small" alpha="70%">({task.size_text})</span>')
        title_label.set_halign(Gtk.Align.START)
        title_label.get_style_context().add_class('task-title')
        header_box.pack_start(title_label, True, True, 0)

        # Cancel button
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.set_size_request(80, -1)
        cancel_btn.connect("clicked", lambda w: self._cancel_task(task))
        header_box.pack_end(cancel_btn, False, False, 0)

        vbox.pack_start(header_box, False, False, 0)

        # Status label
        status_label = Gtk.Label()
        status_label.set_markup('<span size="small">Waiting to start...</span>')
        status_label.set_halign(Gtk.Align.START)
        status_label.get_style_context().add_class('task-status')
        vbox.pack_start(status_label, False, False, 0)

        # Progress bar
        progress_bar = Gtk.ProgressBar()
        progress_bar.set_show_text(True)
        progress_bar.set_text("0%")
        vbox.pack_start(progress_bar, False, False, 0)

        frame.add(vbox)

        # Store widget references
        self.task_widgets[task] = {
            'frame': frame,
            'title': title_label,
            'status': status_label,
            'progress': progress_bar,
            'cancel_btn': cancel_btn
        }

        return frame

    def _cancel_task(self, task):
        """Handle task cancellation."""
        logger.info(f"User cancelled {task.name}")
        task.cancelled = True
        task.cancel_event.set()

        widgets = self.task_widgets[task]
        widgets['status'].set_markup('<span size="small" color="#ff6b6b">❌ Cancelled</span>')
        widgets['cancel_btn'].set_sensitive(False)
        widgets['cancel_btn'].set_label("Cancelled")

    def _update_task_progress(self, task, message, percent):
        """Update progress for a specific task (thread-safe)."""
        def update_ui():
            if task not in self.task_widgets:
                return False

            widgets = self.task_widgets[task]
            widgets['status'].set_markup(f'<span size="small">{message}</span>')
            widgets['progress'].set_fraction(percent / 100.0)
            widgets['progress'].set_text(f"{percent}%")
            return False

        GLib.idle_add(update_ui)

    def _mark_task_complete(self, task, success):
        """Mark a task as complete (thread-safe)."""
        def update_ui():
            if task not in self.task_widgets:
                return False

            task.completed = True
            task.success = success

            widgets = self.task_widgets[task]
            widgets['cancel_btn'].set_sensitive(False)

            if success:
                widgets['status'].set_markup('<span size="small" color="#51cf66">✅ Complete!</span>')
                widgets['progress'].set_fraction(1.0)
                widgets['progress'].set_text("100%")
                widgets['cancel_btn'].set_label("Done")
            else:
                widgets['status'].set_markup('<span size="small" color="#ff6b6b">❌ Failed</span>')
                widgets['cancel_btn'].set_label("Failed")

            # Check if all tasks are done
            self._check_all_complete()
            return False

        GLib.idle_add(update_ui)

    def _check_all_complete(self):
        """Check if all tasks are complete and close dialog if so."""
        all_done = all(task.completed or task.cancelled for task in self.tasks)

        if all_done and not self.all_completed:
            self.all_completed = True
            # Close dialog after short delay
            GLib.timeout_add(1500, lambda: self.dialog.response(Gtk.ResponseType.OK) if self.dialog else False)

    def _run_task(self, task):
        """Run a download task in a background thread."""
        def progress_callback(message, percent):
            self._update_task_progress(task, message, percent)

        def do_download():
            try:
                success = task.download_func(progress_callback, task.cancel_event)
                self._mark_task_complete(task, success)
            except Exception as e:
                logger.error(f"Error in {task.name} download: {e}", exc_info=True)
                self._mark_task_complete(task, False)

        thread = threading.Thread(target=do_download)
        thread.daemon = True
        thread.start()

    def run(self):
        """
        Show the dialog and run all download tasks.

        Returns:
            dict: Results for each task {task_name: (success: bool, cancelled: bool)}
        """
        if not self.tasks:
            logger.warning("No download tasks to run")
            return {}

        # Build the dialog
        self._build_dialog()
        self.dialog.show_all()

        # Start all download tasks
        for task in self.tasks:
            self._run_task(task)

        # Run the dialog (blocks until closed)
        response = self.dialog.run()
        self.dialog.destroy()

        # Return results
        results = {}
        for task in self.tasks:
            results[task.name] = {
                'success': task.success,
                'cancelled': task.cancelled,
                'completed': task.completed
            }

        return results


def show_unified_download_dialog(cuda=False, extension=False, parent=None):
    """
    Convenience function to show unified download dialog.

    Args:
        cuda: Whether to download CUDA libraries
        extension: Whether to install GNOME extension
        parent: Optional parent window

    Returns:
        dict: Download results for each task
    """
    dialog = UnifiedDownloadDialog(parent=parent)

    if cuda:
        from talktype import cuda_helper
        task = DownloadTask(
            name="CUDA Libraries",
            description="GPU acceleration libraries",
            size_text="~800MB",
            download_func=cuda_helper.download_cuda_libraries
        )
        dialog.add_task(task)

    if extension:
        from talktype import extension_helper

        def extension_download(progress_callback, cancel_event):
            """Wrapper for extension installation with progress tracking."""
            progress_callback("Installing GNOME extension...", 30)
            success = extension_helper.install_extension()
            if success:
                progress_callback("Extension installed successfully!", 100)
            else:
                progress_callback("Installation failed", 0)
            return success

        task = DownloadTask(
            name="GNOME Extension",
            description="Native desktop integration",
            size_text="~3KB",
            download_func=extension_download
        )
        dialog.add_task(task)

    return dialog.run()


if __name__ == '__main__':
    # Test the dialog
    import sys
    Gtk.init(sys.argv)

    # Create a test dialog with dummy tasks
    def dummy_download(progress_callback, cancel_event):
        import time
        for i in range(0, 101, 10):
            if cancel_event.is_set():
                return False
            progress_callback(f"Downloading... {i}%", i)
            time.sleep(0.3)
        return True

    dialog = UnifiedDownloadDialog()

    task1 = DownloadTask(
        name="CUDA Libraries",
        description="GPU acceleration",
        size_text="~800MB",
        download_func=dummy_download
    )
    dialog.add_task(task1)

    task2 = DownloadTask(
        name="GNOME Extension",
        description="Desktop integration",
        size_text="~3KB",
        download_func=dummy_download
    )
    dialog.add_task(task2)

    results = dialog.run()
    print(f"Results: {results}")

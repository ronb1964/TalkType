# Gemini Code-Context for TalkType

This document provides a comprehensive overview of the TalkType project, its structure, and key operational commands, intended to be used as a context for AI-assisted development.

## Project Overview

TalkType is a voice dictation application for Linux on Wayland. It uses the `faster-whisper` library for speech-to-text conversion, `sounddevice` for audio recording, `evdev` for listening to hotkeys, and `ydotool` for injecting the transcribed text into other applications.

The project is architecturally divided into three main Python components:

1.  **Core Dictation Service (`src/talktype/app.py`):** This is the backend engine that handles hotkey detection, audio recording, transcription, and text injection. It's designed to run as a background process.

2.  **System Tray Application (`src/talktype/tray.py`):** A GTK-based system tray icon that provides a user interface for starting, stopping, and restarting the dictation service. It also provides access to the preferences window.

3.  **Preferences GUI (`src/talktype/prefs.py`):** A GTK-based graphical interface for configuring the application. Settings are stored in `~/.config/talktype/config.toml`.

## Building and Running

The project uses `poetry` for dependency management and script execution.

*   **Install Dependencies:**
    ```bash
    poetry install
    ```

*   **Run the Application:**
    The main entry point is the tray application, which manages the dictation service.
    ```bash
    poetry run dictate-tray &
    ```

*   **Run Tests:**
    The project uses `pytest` for testing.
    ```bash
    poetry run pytest -q
    ```

*   **Run Individual Components (for development):**
    *   **Dictation Service:** `poetry run dictate`
    *   **Preferences GUI:** `poetry run dictate-prefs`

## Development Conventions

*   **Dependency Management:** Project dependencies are managed with `poetry` and are defined in `pyproject.toml`.
*   **Code Formatting and Linting:** The project is configured to use `black` for code formatting and `ruff` for linting.
*   **Configuration:** Application settings are managed through a `config.toml` file in the user's home directory.
*   **Modularity:** The codebase is well-structured, with clear separation between the core service, the tray application, and the preferences GUI.

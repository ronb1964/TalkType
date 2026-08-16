"""Lightweight logging setup for TalkType."""
import logging
import os
from pathlib import Path

# Roll the log over once it passes this size (checked at process startup).
_MAX_LOG_BYTES = 5 * 1024 * 1024


def _log_dir() -> Path:
    """The dev or production config directory that holds the log.

    DEV_MODE=1 (Ron's daily dev build) logs to ~/.config/talktype-dev/, the
    AppImage to ~/.config/talktype/ — matching config.py's split so the two
    never interleave.
    """
    config_dir = "talktype-dev" if os.environ.get("DEV_MODE") == "1" else "talktype"
    # Inside a Flatpak use the private per-app XDG_CONFIG_HOME so logs don't land
    # in (or read from) a HOST install when --filesystem=home is granted. Host
    # behavior is unchanged (FLATPAK_ID gate). Mirrors config._config_home().
    if os.environ.get("FLATPAK_ID"):
        base = Path(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"))
    else:
        base = Path.home() / ".config"
    return base / config_dir


def log_file_path() -> Path:
    """Absolute path of the active log file."""
    return _log_dir() / "talktype.log"


def clear_log(log_dir: Path = None) -> None:
    """Empty the log: truncate talktype.log to zero and remove its .old backup.

    Truncation rather than deletion is deliberate — the dictation service holds
    the file open in append mode, and on Linux O_APPEND writes always land at the
    real end of file, so after a truncate-to-zero the service simply continues
    at offset 0 instead of leaving a sparse, null-padded file behind.
    """
    d = log_dir or _log_dir()
    try:
        main = d / "talktype.log"
        if main.exists():
            open(main, "w").close()  # truncate in place
    except OSError:
        pass
    try:
        old = d / "talktype.log.old"
        if old.exists():
            old.unlink()
    except OSError:
        pass


def redact_text(text, reveal: bool = False) -> str:
    """Render transcribed text for a log line without leaking it by default.

    The service logs raw and normalized transcriptions to diagnose dictation
    issues, but that means everything the user says would otherwise be written
    to disk in plain text. Redact by default — keep the length as a breadcrumb
    so the log still shows a transcription happened — and only reveal the full
    text (as `repr`, matching the old `{text!r}` output) when the user has
    explicitly opted in via the log_transcripts setting.
    """
    if reveal:
        return repr(text)
    if isinstance(text, str):
        return f"[hidden, {len(text)} chars]"
    return "[hidden]"

def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Create a logger writing to the dev or production log file.

    Honours DEV_MODE so the dev version (DEV_MODE=1) logs to
    ~/.config/talktype-dev/ and the AppImage logs to ~/.config/talktype/ —
    they no longer interleave into one shared file.

    The tray and the dictation service are SEPARATE processes sharing this
    file, so a per-write RotatingFileHandler would race on rollover (lost or
    truncated lines). Instead we do a single atomic rename at startup when the
    file has grown past the cap, then plain append — appends across processes
    are safe, and the rename is atomic so at most one process rolls over.
    """
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Match config.py's dev/prod directory split
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "talktype.log"

    # Startup rollover: bound the log without a per-write rotation race.
    try:
        if log_file.exists() and log_file.stat().st_size > _MAX_LOG_BYTES:
            # os.replace is atomic; if another process already rolled over,
            # the source is gone and this raises (caught) — no double-rename.
            os.replace(log_file, log_dir / "talktype.log.old")
    except OSError:
        pass

    # Plain append-mode file handler (multiprocess-safe for appends)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)

    logger.addHandler(file_handler)

    return logger

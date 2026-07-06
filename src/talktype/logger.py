"""Lightweight logging setup for TalkType."""
import logging
import os
from pathlib import Path

# Roll the log over once it passes this size (checked at process startup).
_MAX_LOG_BYTES = 5 * 1024 * 1024

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
    config_dir = "talktype-dev" if os.environ.get("DEV_MODE") == "1" else "talktype"
    log_dir = Path.home() / ".config" / config_dir
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

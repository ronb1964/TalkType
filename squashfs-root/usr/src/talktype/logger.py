"""Lightweight logging setup for TalkType."""
import logging
import os
from pathlib import Path

def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Create a logger that writes to ~/.config/talktype/talktype.log"""
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Create log directory if it doesn't exist
    log_dir = Path.home() / ".config" / "talktype"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "talktype.log"

    # File handler - detailed logs
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)

    logger.addHandler(file_handler)

    return logger

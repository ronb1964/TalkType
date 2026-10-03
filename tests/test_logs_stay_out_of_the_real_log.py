"""The test suite must never write to the user's real TalkType log.

It used to: every run left fake entries there (a made-up AppImage mount
path, simulated wtype timeouts, "Custom commands applied"), which then looked
like real problems when the log was read to diagnose one (2026-09-29).
"""
import logging
from pathlib import Path

from talktype import logger as talktype_logger


def test_log_file_is_not_in_the_users_config():
    real_config = Path.home() / ".config"
    assert real_config not in talktype_logger.log_file_path().parents


def test_handlers_created_on_import_point_at_the_test_log_dir():
    import talktype.app  # noqa: F401  (imports many modules that set up loggers)
    for name in list(logging.root.manager.loggerDict):
        if not name.startswith("talktype"):
            continue
        for handler in getattr(logging.getLogger(name), "handlers", []):
            if isinstance(handler, logging.FileHandler):
                assert Path.home() / ".config" not in Path(handler.baseFilename).parents, (
                    f"{name} logs to {handler.baseFilename}")

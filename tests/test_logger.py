"""Tests for logger module"""
import os
import logging
from pathlib import Path
from talktype.logger import setup_logger


def test_logger_creation():
    """Test that setup_logger creates a logger"""
    logger = setup_logger("test_module")
    assert logger is not None
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_module"


def test_logger_level():
    """Test that logger is set to INFO level by default"""
    logger = setup_logger("test_level")
    assert logger.level == logging.INFO


def test_logger_has_handlers():
    """Test that logger has file handler"""
    logger = setup_logger("test_handlers")
    # Should have at least one handler (file handler)
    assert len(logger.handlers) >= 1


def test_logger_file_handler_exists(tmp_path):
    """Test that file handler creates log file"""
    # Note: The actual logger writes to ~/.config/talktype/
    # We can't easily change that without modifying the logger module
    # So this test just verifies the handler type exists
    logger = setup_logger("test_file")
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) > 0


def test_logger_file_handler_level():
    """Test that file handler is set to DEBUG level"""
    logger = setup_logger("test_file_level")
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) > 0
    # File handler should be DEBUG level for detailed logs
    assert file_handlers[0].level == logging.DEBUG


def test_logger_singleton_behavior():
    """Test that requesting same logger name returns same instance"""
    logger1 = setup_logger("test_singleton")
    logger2 = setup_logger("test_singleton")
    # Python's logging.getLogger() returns same instance for same name
    assert logger1 is logger2


def test_logger_different_names():
    """Test that different logger names create different loggers"""
    logger1 = setup_logger("test_module_1")
    logger2 = setup_logger("test_module_2")
    assert logger1.name != logger2.name


def test_logger_can_log_messages():
    """Test that logger can actually log messages"""
    logger = setup_logger("test_logging")
    # These should not raise exceptions
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")


def test_logger_format_includes_name():
    """Test that log format includes logger name"""
    logger = setup_logger("test_format")
    # Get the formatter from one of the handlers
    for handler in logger.handlers:
        if handler.formatter:
            format_str = handler.formatter._fmt
            # Should include module name in format
            assert "%(name)s" in format_str or "name" in format_str.lower()
            break

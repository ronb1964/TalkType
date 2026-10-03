"""Test-suite wide setup.

Keep the suite's logging out of the user's real TalkType log. Modules create
their file handler at import time, so this has to happen before any test
module imports talktype, which is why it runs at conftest import rather than
in a fixture. Subprocesses started by tests inherit it through the
environment.
"""
import atexit
import os
import shutil
import tempfile

_LOG_DIR = tempfile.mkdtemp(prefix="talktype-test-logs-")
os.environ["TALKTYPE_LOG_DIR"] = _LOG_DIR
atexit.register(shutil.rmtree, _LOG_DIR, ignore_errors=True)

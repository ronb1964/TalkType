"""The tray's GTK main loop must never block on model loading.

The tray owns the D-Bus name that the dictation service calls into. While its
main loop is blocked it dispatches nothing — and the service makes those calls
from the input thread, holding an exclusive grab on every keyboard. So a slow
call on the tray's main loop does not merely freeze the tray: it can freeze the
user's keyboard system-wide, in every application.

is_model_cached() answers "is this model downloaded?" by constructing a real
WhisperModel, which for large-v3 means seconds to tens of seconds and gigabytes
of RAM. is_model_cached_fast() answers the same question from file presence.
"""

import ast
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "talktype"

# Modules whose code runs on the tray's GTK main loop.
MAIN_LOOP_MODULES = ["tray.py"]

BLOCKING = "is_model_cached"
NON_BLOCKING = "is_model_cached_fast"


def _called_names(path):
    """Every function name called anywhere in the module."""
    tree = ast.parse(path.read_text())
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name:
                names.append((name, node.lineno))
    return names


@pytest.mark.parametrize("module", MAIN_LOOP_MODULES)
def test_main_loop_code_does_not_load_a_model_to_check_the_cache(module):
    path = SRC / module
    offenders = [ln for name, ln in _called_names(path) if name == BLOCKING]

    assert not offenders, (
        f"{module} calls {BLOCKING}() at line(s) {offenders} on the GTK main "
        f"loop. That constructs a real WhisperModel — use {NON_BLOCKING}()."
    )

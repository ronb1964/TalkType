"""GNOME's Alt+F8 / Alt+F7 must always come back.

The hotkey-test dialog disables org.gnome.desktop.wm.keybindings begin-resize
and begin-move so they don't fight the key capture, then restores them after
dialog.run(). Everything in between was unprotected: any exception — building
the dialog, starting a thread, the X server hiccuping — skipped the restore
and left the user's window keybindings disabled permanently, as a persisted
gsettings value that survives reboots, with nothing pointing at TalkType.
"""

import ast
import pathlib

from talktype import welcome_dialog as W

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "talktype"


def test_restore_sets_both_bindings_back(monkeypatch):
    calls = []
    monkeypatch.setattr(W.subprocess, "run", lambda cmd, **k: calls.append(cmd))

    W._restore_gnome_keybindings("['<Alt>F8']", "['<Alt>F7']")

    joined = [" ".join(c) for c in calls]
    assert any("begin-resize ['<Alt>F8']" in c for c in joined)
    assert any("begin-move ['<Alt>F7']" in c for c in joined)


def test_restore_skips_values_that_were_never_captured(monkeypatch):
    """None means we never successfully read the old value — writing a
    guess would be worse than leaving it."""
    calls = []
    monkeypatch.setattr(W.subprocess, "run", lambda cmd, **k: calls.append(cmd))

    W._restore_gnome_keybindings(None, None)

    assert calls == []


def test_restore_survives_gsettings_failing(monkeypatch):
    """Called from a finally block — it must never raise on the way out."""
    def boom(cmd, **k):
        raise OSError("gsettings not found")

    monkeypatch.setattr(W.subprocess, "run", boom)

    W._restore_gnome_keybindings("['<Alt>F8']", "['<Alt>F7']")   # must not raise


def test_restore_still_tries_the_second_binding_if_the_first_fails(monkeypatch):
    seen = []

    def flaky(cmd, **k):
        seen.append(cmd)
        if "begin-resize" in cmd:
            raise OSError("transient")

    monkeypatch.setattr(W.subprocess, "run", flaky)

    W._restore_gnome_keybindings("['<Alt>F8']", "['<Alt>F7']")

    assert any("begin-move" in c for c in seen), "gave up after the first failure"


def test_the_restore_runs_from_a_finally_block():
    """Structural guard: the restore must not sit on the happy path only."""
    tree = ast.parse((SRC / "welcome_dialog.py").read_text())

    in_finally = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for stmt in node.finalbody:
                for sub in ast.walk(stmt):
                    if (isinstance(sub, ast.Call)
                            and getattr(sub.func, "id", "") == "_restore_gnome_keybindings"):
                        in_finally = True

    assert in_finally, (
        "_restore_gnome_keybindings() is not called from a finally block — an "
        "exception would leave the user's GNOME keybindings disabled for good"
    )

"""`python -m talktype.app` must run the whole service in ONE module object.

Running the dictation service as `python -m talktype.app` executes app.py under
the name "__main__". But the input backends reach the app via
`from . import app` — module "talktype.app" — which is a SEPARATE module object
with its own globals. main() assigns model, _custom_commands, dbus_service,
_typing_delay and friends as module globals; if main() runs in "__main__" while
the recording loop runs in "talktype.app", every one of those globals is
invisible over there and transcription dies with `NameError: name 'model'`.

The Backend B seam first exposed this: BB-6's main() called _loop_evdev()
directly (same namespace, worked); BB-8 routed the entry through
EvdevInputBackend.start(), which does `from . import app`, so the loop began
running in "talktype.app" while main() had set its globals in "__main__".

The AppImage's bin/dictate never hit it — a setuptools console script that does
`from talktype.app import main`, the correct package name. The `-m` entry must
behave the same by delegating to the package module's main(). BB-9's Flatpak
also launches with `python3 -m talktype.app`, so this guard protects it too.
"""

import subprocess
import sys
import textwrap


def test_entry_helper_runs_the_package_modules_main(monkeypatch):
    """_run_service_entry() must invoke talktype.app.main, so main() executes in
    the package module — the very object the input backends import."""
    from talktype import app

    ran_in = {}
    monkeypatch.setattr(app, "main", lambda: ran_in.setdefault("module", app))

    app._run_service_entry()

    assert ran_in.get("module") is app, (
        "the module entry did not run the package module's main(); a "
        "`python -m talktype.app` launch would split the app into two module "
        "objects and the recording loop would never see the `model` global."
    )


def test_dash_m_entry_delegates_to_package_module():
    """End to end: executing app.py as "__main__" (as `python -m` does) must
    call talktype.app.main, not a second local main() defined in "__main__".

    The child pre-imports talktype.app and replaces its main() with a probe that
    raises the moment it is called. After the fix the "__main__" guard delegates
    through `from talktype.app import main`, so the probe fires and we confirm
    both that it ran and that it is the same module the backends import.
    """
    child = textwrap.dedent(
        """
        import runpy
        import sys

        import talktype.app as pkg  # the canonical module the backends import

        class _Delegated(Exception):
            pass

        def _probe():
            # main() must be THIS package module's main (identity check),
            # never a duplicate defined in the "__main__" execution.
            raise _Delegated(sys.modules["talktype.app"] is pkg)

        pkg.main = _probe

        try:
            runpy.run_module("talktype.app", run_name="__main__", alter_sys=True)
        except _Delegated as exc:
            print("DELEGATED", bool(exc.args[0]))
        else:
            print("NOT_DELEGATED")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", child],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "DELEGATED True" in result.stdout, (
        "`python -m talktype.app` did not delegate to talktype.app.main "
        f"(stdout={result.stdout!r} stderr={result.stderr[-800:]!r})"
    )

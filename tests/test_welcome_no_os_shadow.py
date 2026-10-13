"""show_welcome_and_install must use the module-level `os` and `GLib`.

A local `import os` anywhere inside show_welcome_and_install makes `os`
function-local for the WHOLE function, so the earlier
`os.environ.get("FLATPAK_ID")` (the hotkey-test skip) throws UnboundLocalError,
which silently aborts onboarding right after "Let's Go!" and leaves the tray
icon slashed with nothing else happening.

If `os` ever becomes a local in that function again, this fails.
"""
from tuxtalk import welcome_dialog


def test_show_welcome_and_install_uses_module_level_os():
    code = welcome_dialog.show_welcome_and_install.__code__
    assert "os" not in code.co_varnames, (
        "os is function-local in show_welcome_and_install — a stray `import os` "
        "will crash the earlier os.environ use with UnboundLocalError and abort "
        "onboarding after 'Let's Go!'. Use the module-level os."
    )


def test_show_welcome_and_install_uses_module_level_glib():
    """The AppImage-copy thread inside it calls GLib.idle_add when the copy
    fails. A local `from gi.repository import GLib` further down would make
    GLib a not-yet-assigned closure variable there, so that call would raise
    NameError."""
    code = welcome_dialog.show_welcome_and_install.__code__
    assert "GLib" not in code.co_varnames + code.co_cellvars

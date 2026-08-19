"""Regression guard for a subtle onboarding-killer.

A local `import os` added inside show_welcome_and_install (with the KDE
notification-help hook) made `os` function-local for the WHOLE function, so the
earlier `os.environ.get("FLATPAK_ID")` (the hotkey-test skip) threw
UnboundLocalError — which silently aborted onboarding right after "Let's Go!",
leaving the tray icon slashed and nothing else happening.

If `os` ever becomes a local in that function again, this fails.
"""
from talktype import welcome_dialog


def test_show_welcome_and_install_uses_module_level_os():
    code = welcome_dialog.show_welcome_and_install.__code__
    assert "os" not in code.co_varnames, (
        "os is function-local in show_welcome_and_install — a stray `import os` "
        "will crash the earlier os.environ use with UnboundLocalError and abort "
        "onboarding after 'Let's Go!'. Use the module-level os."
    )

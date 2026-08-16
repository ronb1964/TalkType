"""set_autostart writes an autostart .desktop that relaunches via the wrapper.

Onboarding and Preferences both call this. The enabled file must carry the real
launch command (the env-setting wrapper, not bare Python) and be marked as an
enabled autostart entry; disabling must write a Hidden=true stub rather than
leaving a live entry behind.
"""

import pytest

from talktype import autostart


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    path = tmp_path / "autostart" / "talktype.desktop"
    monkeypatch.setattr(autostart, "_autostart_desktop_path", lambda: str(path))
    monkeypatch.setattr(autostart, "get_launch_command", lambda: "/usr/bin/talktype")
    monkeypatch.setattr(autostart, "get_icon_path", lambda: "/icons/talktype.svg")
    return path


def test_enable_writes_wrapper_launch_command(desktop):
    assert autostart.set_autostart(True) is True
    text = desktop.read_text()
    assert "Exec=/usr/bin/talktype" in text
    assert "X-GNOME-Autostart-enabled=true" in text
    assert "Hidden=true" not in text
    # Must NOT be the bare-Python line that fails at login.
    assert "python3 -m talktype.tray" not in text


def test_disable_writes_hidden_stub(desktop):
    autostart.set_autostart(True)
    assert autostart.set_autostart(False) is True
    text = desktop.read_text()
    assert "Hidden=true" in text
    assert "Exec=/usr/bin/talktype" not in text


def test_enable_creates_missing_directory(desktop):
    # Parent dir does not exist yet; set_autostart must create it.
    assert not desktop.parent.exists()
    assert autostart.set_autostart(True) is True
    assert desktop.exists()

"""On the Flatpak the dictation keys are owned by the desktop's global-shortcuts
portal, not TalkType's config — so Preferences must point the user at the right
place to change them instead of showing an editable (and wrong) F8/F9 combo."""

from talktype.desktop_detect import flatpak_hotkey_hint


def test_hint_kde_points_to_system_settings(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    hint = flatpak_hotkey_hint()
    assert "System Settings" in hint
    assert "TalkType" in hint


def test_hint_gnome_points_to_keyboard_settings(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    hint = flatpak_hotkey_hint()
    assert "Keyboard" in hint
    assert "TalkType" in hint


def test_hint_unknown_desktop_is_generic(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "XFCE")
    hint = flatpak_hotkey_hint()
    assert "shortcut" in hint.lower()

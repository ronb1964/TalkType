"""The daily check's extension-update notice points to where it installs.

It said "Click 'Check for Updates' in menu for details", but that dialog
covers only the app, so it answered "You're up to date". Extension updates
are installed from Preferences → Updates & Backup.
"""
from tuxtalk import tray


def test_the_notice_points_to_updates_and_backup(monkeypatch):
    shown = []
    monkeypatch.setattr("tuxtalk.notify.notify", lambda title, body: shown.append((title, body)))
    assert tray.DictationTray._show_update_notification(object()) is False
    (title, body), = shown
    assert "Updates & Backup" in body and "Check for Updates" not in body

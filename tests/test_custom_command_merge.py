"""Preferences must not undo a fix saved while it was open.

Preferences loads the voice commands when it opens and used to write that
whole list back on Apply/OK. A word fixed from the tray (Fix a Word) while
Preferences was open was therefore deleted by the next Apply. It now applies
only the user's own edits on top of what is on disk at save time.
"""
from talktype.config import merge_custom_command_edits as merge


def test_fix_saved_elsewhere_survives_an_unrelated_apply():
    loaded = {"my email": "me@example.com"}
    on_screen = dict(loaded)                        # user changed nothing here
    on_disk = {"my email": "me@example.com", "bamboo studio": "BambuStudio"}
    assert merge(loaded, on_screen, on_disk) == on_disk


def test_users_own_edits_still_win():
    loaded = {"my email": "old@example.com", "sig": "Ron"}
    on_screen = {"my email": "new@example.com", "brb": "be right back"}  # edited, removed sig, added brb
    on_disk = {"my email": "old@example.com", "sig": "Ron", "gift tarot": "Giftara"}
    assert merge(loaded, on_screen, on_disk) == {
        "my email": "new@example.com",
        "brb": "be right back",
        "gift tarot": "Giftara",
    }


def test_nothing_on_disk_changed_is_the_plain_old_behaviour():
    loaded = {"a": "1", "b": "2"}
    on_screen = {"a": "1", "c": "3"}
    assert merge(loaded, on_screen, dict(loaded)) == {"a": "1", "c": "3"}

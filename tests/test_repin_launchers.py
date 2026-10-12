"""Pinned dock and favourite entries follow the rename (0.15.0).

The migration renames the menu entry (talktype.desktop -> tuxtalk.desktop).
A dock that pinned the old name then shows a blank icon on KDE (Ron saw it on
his own panel), and GNOME silently drops it from the favourites. So the pinned
lists are rewritten too, once.
"""
from tuxtalk import rename_migration as rm


def test_pinned_entries_are_renamed_in_place():
    items = ["applications:systemsettings.desktop", "applications:talktype-dev.desktop",
             "preferred://browser"]
    new, changed = rm.renamed_launchers(items)
    assert new == ["applications:systemsettings.desktop", "applications:tuxtalk-dev.desktop",
                   "preferred://browser"]
    assert changed


def test_every_old_launcher_name_is_covered():
    for old, new in (("talktype.desktop", "tuxtalk.desktop"),
                     ("io.github.ronb1964.TalkType.desktop", "io.github.ronb1964.TuxTalk.desktop"),
                     ("talktype-dev.desktop", "tuxtalk-dev.desktop")):
        assert rm.renamed_launchers([old])[0] == [new]                       # GNOME favourites
        assert rm.renamed_launchers([f"applications:{old}"])[0] == [f"applications:{new}"]  # KDE


def test_a_list_already_pinning_tuxtalk_does_not_get_it_twice():
    new, changed = rm.renamed_launchers(["tuxtalk.desktop", "talktype.desktop"])
    assert new == ["tuxtalk.desktop"] and changed


def test_nothing_to_rename_changes_nothing():
    assert rm.renamed_launchers(["firefox.desktop"]) == (["firefox.desktop"], False)


def test_repin_runs_once_and_uses_both_desktops(tmp_path):
    marker = tmp_path / "launchers-renamed"
    calls = []
    favs = {"v": ["org.gnome.Nautilus.desktop", "talktype.desktop"]}

    def plasma(script):
        calls.append(script)
        return "1"
    lines = rm.repin_launchers(str(marker), run_plasma_script=plasma,
                               gnome_favorites=(lambda: favs["v"], lambda v: favs.update(v=v)))
    assert favs["v"] == ["org.gnome.Nautilus.desktop", "tuxtalk.desktop"]
    assert "applications:talktype-dev.desktop" in calls[0]     # the KDE script carries the map
    assert marker.exists() and lines
    assert rm.repin_launchers(str(marker), run_plasma_script=plasma) == []   # once only
    assert len(calls) == 1


def test_a_failure_leaves_it_to_try_again_next_start(tmp_path):
    marker = tmp_path / "launchers-renamed"

    def broken(script):
        raise RuntimeError("plasmashell not running yet")
    rm.repin_launchers(str(marker), run_plasma_script=broken, gnome_favorites=None)
    assert not marker.exists()


def test_tray_repins_on_start():
    import pathlib
    src = (pathlib.Path(rm.__file__).parent / "tray.py").read_text()
    main = src[src.index("def main():"):]
    assert "repin_launchers(" in main[:3500]

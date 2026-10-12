"""An installed TalkType becomes TuxTalk in place (0.15.0 rename).

A 0.14.x updater saves the new AppImage under the OLD name
(~/AppImages/TalkType.AppImage) and restarts it. The new version then moves
its own file, the Applications-menu launcher and the launch-at-login entry to
the new names, keeping whether launch-at-login was on or off exactly.
"""
import os

from tuxtalk import rename_migration as rm


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _entry(exec_line, enabled="true", name="TalkType"):
    return ("[Desktop Entry]\nType=Application\n"
            f"Name={name}\n"
            "Comment=AI-powered dictation for Wayland using Faster-Whisper\n"
            f"Exec={exec_line}\nIcon=talktype\n"
            f"X-GNOME-Autostart-enabled={enabled}\n")


def _old_appimage_install(h, enabled="true"):
    _write(f"{h}/AppImages/TalkType.AppImage", "ELF")
    _write(f"{h}/.config/autostart/talktype.desktop", _entry(f"{h}/AppImages/TalkType.AppImage", enabled))
    _write(f"{h}/.local/share/applications/talktype.desktop", _entry(f"{h}/AppImages/TalkType.AppImage"))


def test_appimage_launcher_and_autostart_move_to_tuxtalk(tmp_path):
    h = str(tmp_path)
    _old_appimage_install(h)
    # A 0.14.x updater saved the new version under the old name and started it.
    rm.adopt_old_install(home=h, running_appimage=f"{h}/AppImages/TalkType.AppImage")
    assert open(f"{h}/AppImages/TuxTalk.AppImage").read() == "ELF"
    assert os.path.islink(f"{h}/AppImages/TalkType.AppImage")
    auto = open(f"{h}/.config/autostart/tuxtalk.desktop").read()
    assert f"Exec={h}/AppImages/TuxTalk.AppImage\n" in auto
    assert "X-GNOME-Autostart-enabled=true" in auto
    assert "Name=TuxTalk\n" in auto
    assert "Faster-Whisper" not in auto
    assert not os.path.exists(f"{h}/.config/autostart/talktype.desktop")
    menu = open(f"{h}/.local/share/applications/tuxtalk.desktop").read()
    assert f"Exec={h}/AppImages/TuxTalk.AppImage\n" in menu and "Name=TuxTalk\n" in menu
    assert not os.path.exists(f"{h}/.local/share/applications/talktype.desktop")


def test_launch_at_login_that_was_off_stays_off(tmp_path):
    h = str(tmp_path)
    _old_appimage_install(h, enabled="false")
    rm.adopt_old_install(home=h)
    assert "X-GNOME-Autostart-enabled=false" in open(f"{h}/.config/autostart/tuxtalk.desktop").read()


def test_existing_tuxtalk_appimage_is_never_overwritten(tmp_path):
    h = str(tmp_path)
    _old_appimage_install(h)
    _write(f"{h}/AppImages/TuxTalk.AppImage", "NEWER")
    rm.adopt_old_install(home=h)
    assert open(f"{h}/AppImages/TuxTalk.AppImage").read() == "NEWER"
    assert open(f"{h}/AppImages/TalkType.AppImage").read() == "ELF"   # left alone


def test_an_old_autostart_next_to_a_new_one_is_removed(tmp_path):
    # Two login entries would start two copies (the shared lock stops the
    # second, but the old entry must not linger).
    h = str(tmp_path)
    _old_appimage_install(h)
    _write(f"{h}/.config/autostart/tuxtalk.desktop", _entry("/x/TuxTalk.AppImage", name="TuxTalk"))
    rm.adopt_old_install(home=h)
    assert not os.path.exists(f"{h}/.config/autostart/talktype.desktop")
    assert "Exec=/x/TuxTalk.AppImage" in open(f"{h}/.config/autostart/tuxtalk.desktop").read()


def test_dev_entries_move_and_keep_their_command(tmp_path):
    h = str(tmp_path)
    dev_exec = "/home/ron/Projects/TalkType/run-dev.sh"
    _write(f"{h}/.config/autostart/talktype-dev.desktop", _entry(dev_exec, name="TalkType (Dev)"))
    _write(f"{h}/.local/share/applications/talktype-dev.desktop", _entry(dev_exec, name="TalkType (Dev)"))
    rm.adopt_old_install(home=h, dev=True)
    for d in (".config/autostart", ".local/share/applications"):
        text = open(f"{h}/{d}/tuxtalk-dev.desktop").read()
        assert f"Exec={dev_exec}\n" in text            # the project folder keeps its name
        assert "Name=TuxTalk (Dev)\n" in text
        assert not os.path.exists(f"{h}/{d}/talktype-dev.desktop")


def test_second_run_does_nothing(tmp_path):
    h = str(tmp_path)
    _old_appimage_install(h)
    rm.adopt_old_install(home=h)
    assert rm.adopt_old_install(home=h) == []


def test_tray_adopts_the_old_install_on_start():
    import pathlib
    src = (pathlib.Path(rm.__file__).parent / "tray.py").read_text()
    main = src[src.index("def main():"):]
    assert "adopt_old_install(" in main[:3000]

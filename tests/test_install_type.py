"""Tests for install-type detection in update_checker.

The updater must know HOW TalkType was installed so it never tries to download
and run an AppImage on a .deb/.rpm/AUR/Flatpak install (that fails, e.g. missing
libfuse.so.2 on Fedora). get_install_type() is fully injectable so these tests
never touch the real environment.
"""
from talktype.update_checker import get_install_type, get_update_guidance


def test_flatpak_detected_from_env():
    assert get_install_type(flatpak_env="io.github.ronb1964.TalkType",
                            appimage_env="", module_path="/app/lib/x.py") == "flatpak"


def test_aur_is_appimage_under_opt():
    # AUR ships the AppImage to /opt/talktype/TalkType.AppImage (pacman-managed)
    assert get_install_type(appimage_env="/opt/talktype/TalkType.AppImage",
                            module_path="/tmp/.mount_abc/usr/src/talktype/u.py") == "aur"


def test_self_managed_appimage_under_home():
    assert get_install_type(appimage_env="/home/ron/AppImages/TalkType.AppImage",
                            module_path="/tmp/.mount_abc/usr/src/talktype/u.py") == "appimage"


def test_rpm_package_from_opt_tree():
    # .deb/.rpm ship the EXTRACTED tree; APPIMAGE is unset, source lives in /opt/talktype
    assert get_install_type(appimage_env="", flatpak_env="",
                            module_path="/opt/talktype/usr/src/talktype/update_checker.py",
                            pkg_query=lambda: "rpm") == "rpm"


def test_deb_package_from_opt_tree():
    assert get_install_type(appimage_env="", flatpak_env="",
                            module_path="/opt/talktype/usr/src/talktype/update_checker.py",
                            pkg_query=lambda: "deb") == "deb"


def test_generic_package_when_manager_unknown():
    assert get_install_type(appimage_env="", flatpak_env="",
                            module_path="/opt/talktype/usr/src/talktype/update_checker.py",
                            pkg_query=lambda: None) == "package"


def test_dev_checkout():
    assert get_install_type(appimage_env="", flatpak_env="",
                            module_path="/home/ron/Projects/TalkType/src/talktype/update_checker.py",
                            pkg_query=lambda: None) == "dev"


def test_guidance_appimage_can_auto_update():
    g = get_update_guidance("appimage", "0.8.0")
    assert g["can_auto_update"] is True


def test_guidance_rpm_gives_dnf_command_no_auto():
    g = get_update_guidance("rpm", "0.8.0")
    assert g["can_auto_update"] is False
    assert "dnf" in g["command"]
    assert "0.8.0" in g["message"]


def test_guidance_deb_gives_apt_command():
    g = get_update_guidance("deb", "0.8.0")
    assert g["can_auto_update"] is False
    assert "apt" in g["command"]


def test_guidance_aur_gives_helper_command():
    g = get_update_guidance("aur", "0.8.0")
    assert g["can_auto_update"] is False
    assert "talktype-appimage" in g["command"]


def test_guidance_flatpak_gives_flatpak_command():
    g = get_update_guidance("flatpak", "0.8.0")
    assert g["can_auto_update"] is False
    assert "flatpak update" in g["command"]

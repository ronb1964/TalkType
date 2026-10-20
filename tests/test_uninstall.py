"""Uninstalling TuxTalk (uninstall.py, packaging/before-remove.sh).

Every test works in a made-up home folder; nothing here may touch the
real one, and conftest.py fails any test that reaches pkexec.
"""
import os
import pathlib
import re
import subprocess

import pytest

from tuxtalk import control, secure_input, uinput_helper, uninstall

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A home folder with what a TuxTalk AppImage leaves after a while."""
    home = tmp_path / "home"
    data = home / ".local/share/TuxTalk"
    for folder in ("cuda/lib", "whisper-vulkan/1.9.5", "parakeet-ultra", "ai-engine", "kwin"):
        (data / folder).mkdir(parents=True)
        (data / folder / "file").write_text("downloaded")
    (data / ".first_run_done").write_text("")
    (data / "stats.json").write_text("{}")
    (data / "recent-transcripts.json").write_text("[]")
    config = home / ".config/tuxtalk"
    config.mkdir(parents=True)
    (config / "config.toml").write_text("model = 'parakeet-v3'\n")
    (config / "custom_words.txt").write_text("TuxTalk\n")
    hub = home / ".cache/huggingface/hub"
    for repo in ("models--Systran--faster-whisper-small", "models--Qwen--Qwen2.5-1.5B-Instruct-GGUF",
                 ".locks/models--Systran--faster-whisper-small",
                 "models--someone--another-apps-model"):
        (hub / repo).mkdir(parents=True)
    (home / "AppImages").mkdir()
    (home / "AppImages/TuxTalk.AppImage").write_text("program")
    (home / "AppImages/TalkType.AppImage").symlink_to("TuxTalk.AppImage")
    for path in (".config/autostart/tuxtalk.desktop", ".local/share/applications/tuxtalk.desktop",
                 ".local/share/icons/hicolor/256x256/apps/tuxtalk.png"):
        (home / path).parent.mkdir(parents=True, exist_ok=True)
        (home / path).write_text("")
    (home / "Documents").mkdir()
    (home / "Documents/TuxTalk-settings-2026-10-20-0900.zip").write_text("a backup")

    # This machine's own helper, extension folder and groups stay out of it.
    for name in ("UNIT_PATH", "HELPER_PATH", "UINPUT_RULE_PATH"):
        monkeypatch.setattr(secure_input, name, str(tmp_path / f"etc-{name}"))
    monkeypatch.setattr(uinput_helper, "UDEV_RULE_PATH", str(tmp_path / "etc-99-rule"))
    monkeypatch.setattr(uninstall.desktop_detect, "get_extension_dir",
                        lambda: str(home / ".local/share/gnome-shell/extensions"))
    return home


def _find(home, install_type="appimage", **kwargs):
    environ = {"XDG_RUNTIME_DIR": str(home.parent / "run")}
    return uninstall.find(home, install_type, environ=environ, **kwargs)


def _left(home):
    return sorted(str(p.relative_to(home)) for p in home.rglob("*"))


def test_downloads_and_launchers_go_and_settings_stay(home):
    plan = _find(home)
    uninstall.remove_files(plan, delete_personal=False)
    assert _left(home) == sorted([
        ".cache", ".cache/huggingface", ".cache/huggingface/hub",
        ".cache/huggingface/hub/models--someone--another-apps-model",
        ".config", ".config/autostart", ".config/tuxtalk",
        ".config/tuxtalk/config.toml", ".config/tuxtalk/custom_words.txt",
        ".local", ".local/share", ".local/share/TuxTalk",
        ".local/share/TuxTalk/recent-transcripts.json", ".local/share/TuxTalk/stats.json",
        ".local/share/applications", ".local/share/icons", ".local/share/icons/hicolor",
        ".local/share/icons/hicolor/256x256", ".local/share/icons/hicolor/256x256/apps",
        "Documents", "Documents/TuxTalk-settings-2026-10-20-0900.zip"])


def test_asked_to_it_leaves_nothing_of_tuxtalk_but_the_saved_backup(home):
    plan = _find(home)
    uninstall.remove_files(plan, delete_personal=True)
    left = _left(home)
    assert not [p for p in left if "tuxtalk" in p.lower() and not p.startswith("Documents")]
    assert "Documents/TuxTalk-settings-2026-10-20-0900.zip" in left
    assert ".cache/huggingface/hub/models--someone--another-apps-model" in left


def test_models_moved_to_another_disk_are_deleted_there_too(home, tmp_path):
    data = home / ".local/share/TuxTalk"
    big_disk = tmp_path / "bigdisk/TuxTalk"
    big_disk.parent.mkdir()
    data.rename(big_disk)
    data.symlink_to(big_disk)
    plan = _find(home)
    uninstall.remove_files(plan, delete_personal=False)
    assert sorted(p.name for p in big_disk.iterdir()) == ["recent-transcripts.json", "stats.json"]
    uninstall.remove_files(_find(home), delete_personal=True)
    assert not os.path.lexists(data) and not big_disk.exists()


def test_the_running_appimage_goes_but_the_aur_packages_copy_is_pacmans(home, tmp_path):
    downloaded = home / "Downloads/TuxTalk-v0.17.0-x86_64.AppImage"
    downloaded.parent.mkdir()
    downloaded.write_text("program")
    assert downloaded in _find(home, appimage=str(downloaded)).leftovers
    assert downloaded not in _find(home, "aur", appimage=str(downloaded)).leftovers


def test_only_tuxtalks_own_ydotoold_unit_is_removed(home):
    unit = home / ".config/systemd/user/ydotoold.service"
    unit.parent.mkdir(parents=True)
    unit.write_text(uinput_helper.YDOTOOLD_SERVICE_TEMPLATE.format(ydotoold_path="/usr/bin/ydotoold"))
    assert _find(home).ydotoold_unit == unit
    unit.write_text("[Unit]\nDescription=Someone's own ydotoold\n")
    assert _find(home).ydotoold_unit is None


def test_every_file_in_the_data_folder_is_sorted_into_personal_or_not():
    """A new file in the data folder has to be put in PERSONAL_DATA (kept
    unless asked) or here (always deleted), so nobody's data is deleted
    by surprise."""
    rebuilt = {"cuda", "ai-engine", "parakeet-ultra", "whisper-vulkan", "kwin",
               ".first_run_done", ".hotkey_test_mode", "remote_desktop_token"}
    names = set()
    for source in (ROOT / "src/tuxtalk").glob("*.py"):
        names |= set(re.findall(r'get_data_dir\(\),\s*"([^"]+)"', source.read_text()))
    assert names, "the pattern no longer finds the data folder's files"
    assert names <= rebuilt | set(uninstall.PERSONAL_DATA), names - rebuilt


def test_the_hugging_face_cache_follows_its_own_settings(tmp_path):
    home = tmp_path
    assert uninstall.hf_hub_cache(home, {}) == home / ".cache/huggingface/hub"
    assert uninstall.hf_hub_cache(home, {"XDG_CACHE_HOME": "/c"}) == pathlib.Path("/c/huggingface/hub")
    assert uninstall.hf_hub_cache(home, {"HF_HOME": "/h", "XDG_CACHE_HOME": "/c"}) == pathlib.Path("/h/hub")
    assert uninstall.hf_hub_cache(home, {"HF_HUB_CACHE": "/x", "HF_HOME": "/h"}) == pathlib.Path("/x")


@pytest.mark.parametrize("install_type,command", [
    ("deb", "apt-get remove -y tuxtalk"),
    ("rpm", "dnf remove -y tuxtalk"),
    ("aur", "pacman -R --noconfirm tuxtalk-appimage"),
])
def test_the_root_script_removes_the_package_last(home, install_type, command):
    script = uninstall.root_script(_find(home, install_type), leave_group=False)
    assert subprocess.run(["bash", "-n"], input=script, text=True).returncode == 0
    assert script.index(secure_input.UNIT_PATH) < script.index(command)
    assert "gpasswd" not in script


def test_an_appimage_has_no_package_to_remove_and_leaving_the_group_is_asked_for(home):
    script = uninstall.root_script(_find(home), leave_group=True)
    assert "apt-get" not in script and "pacman" not in script
    assert 'gpasswd -d "$(id -nu "${PKEXEC_UID:?}")" input' in script


def test_a_package_manager_that_refuses_is_reported(home, tmp_path):
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "apt-get").write_text("#!/bin/sh\necho 'E: Could not get lock /var/lib/dpkg/lock'\nexit 100\n")
    (fake / "apt-get").chmod(0o755)
    lines = uninstall._package_lines(_find(home, "deb"))
    ran = subprocess.run(["bash", "-c", lines], capture_output=True, text=True,
                         env={"PATH": f"{fake}:/usr/bin:/bin"})
    assert secure_input.PACKAGE_NOT_REMOVED in ran.stdout
    assert "Could not get lock" in ran.stdout


def test_pkexec_passes_the_package_failure_on(monkeypatch):
    class Done:
        returncode, stdout, stderr = 0, secure_input.PACKAGE_NOT_REMOVED + "\nE: busy\n", ""
    monkeypatch.setattr(secure_input.subprocess, "run", lambda *a, **k: Done())
    assert secure_input._pkexec("true", "tested") == (True, secure_input.PACKAGE_NOT_REMOVED)


def test_the_question_lists_only_what_this_computer_has(home):
    plan = _find(home)
    text = uninstall.confirm_text(plan, 2_500_000_000)
    assert "TuxTalk itself (its AppImage)" in text
    assert "(2.5 GB)" in text
    assert "hotkey helper" not in text and "GNOME extension" not in text
    pathlib.Path(secure_input.UNIT_PATH).write_text("")
    (home / ".local/share/gnome-shell/extensions/talktype@ronb1964.github.io").mkdir(parents=True)
    text = uninstall.confirm_text(_find(home, "deb"), 1)
    assert "the tuxtalk package" in text and "hotkey helper" in text and "GNOME extension" in text


def test_the_closing_message_says_how_to_finish_a_refused_package(home):
    text = uninstall.done_text(_find(home, "rpm"), delete_personal=True, left_group=False,
                               package_failed=True)
    assert "sudo dnf remove tuxtalk" in text
    assert "Log out" not in text


def test_tuxtalk_minus_minus_uninstall():
    assert control.parse_open(["--uninstall"]) == "uninstall"
    with pytest.raises(SystemExit):
        control.parse_open(["--open", "uninstall"])


def _run_before_remove(tmp_path, arg):
    """packaging/before-remove.sh with every command it runs recorded, not run."""
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    log = tmp_path / "ran.log"
    for name in ("rm", "rmdir", "systemctl", "udevadm"):
        (fake / name).write_text(f'#!/bin/sh\necho "{name} $*" >> {log}\n')
        (fake / name).chmod(0o755)
    subprocess.run(["sh", str(ROOT / "packaging/before-remove.sh"), arg], check=True,
                   env={"PATH": f"{fake}:/usr/bin:/bin"})
    return log.read_text() if log.exists() else ""


@pytest.mark.parametrize("arg", ["upgrade", "1", "failed-upgrade"])
def test_a_package_upgrade_keeps_the_hotkey_helper(tmp_path, arg):
    assert _run_before_remove(tmp_path, arg) == ""


@pytest.mark.parametrize("arg", ["remove", "0"])
def test_removing_the_package_removes_the_hotkey_helper_and_rules(tmp_path, arg):
    ran = _run_before_remove(tmp_path, arg)
    assert "systemctl disable --now tuxtalk-hotkeys.service" in ran
    for path in (secure_input.UNIT_PATH, secure_input.HELPER_PATH,
                 secure_input.UINPUT_RULE_PATH, uinput_helper.UDEV_RULE_PATH):
        assert path in ran


@pytest.mark.parametrize("script", ["packaging/before-remove.sh",
                                    "aur-repo-tuxtalk/tuxtalk-appimage.install"])
def test_the_package_scripts_name_the_same_files_as_the_app(script):
    path = ROOT / script
    if not path.exists():
        pytest.skip("the AUR clone isn't part of the repository")
    text = path.read_text()
    for name in (secure_input.SERVICE, secure_input.UNIT_PATH, secure_input.HELPER_PATH,
                 secure_input.HELPER_DIR, secure_input.UINPUT_RULE_PATH, uinput_helper.UDEV_RULE_PATH):
        assert name in text


def test_both_packages_run_the_removal_script():
    for name in ("build-deb.sh", "build-rpm.sh"):
        assert '--before-remove "$PROJECT_DIR/packaging/before-remove.sh"' in (ROOT / name).read_text()


def test_a_second_uninstall_request_while_asking_opens_no_second_question(monkeypatch):
    """Clicking Uninstall TuxTalk... again while the question is up (or
    tuxtalk --uninstall beside it) once stacked a second question inside
    the first one's dialog loop, and neither could close."""
    import types
    from tuxtalk import tray as tray_mod
    t = types.SimpleNamespace(_uninstalling=False, _shut_down=lambda: None,
                              _leave_main_loop=lambda: None)
    asked = []

    def run(stop_tray_parts):
        asked.append(1)
        tray_mod.DictationTray.uninstall(t)      # the second request, from inside the first
        return False
    monkeypatch.setattr(uninstall, "run", run)
    tray_mod.DictationTray.uninstall(t)
    assert asked == [1]
    assert t._uninstalling is False              # and the next request is asked again

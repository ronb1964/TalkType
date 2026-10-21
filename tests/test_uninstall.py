"""Uninstalling TuxTalk (uninstall.py, packaging/before-remove.sh).

Every test works in a made-up home folder; nothing here may touch the
real one, and conftest.py fails any test that reaches pkexec.
"""
import os
import pathlib
import re
import subprocess
import types

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


HUB = ".cache/huggingface/hub"


def test_downloads_and_launchers_go_and_settings_and_shared_models_stay(home):
    plan = _find(home)
    uninstall.remove_files(plan, delete_personal=False, delete_shared=False)
    assert _left(home) == sorted([
        ".cache", ".cache/huggingface", HUB, f"{HUB}/.locks",
        f"{HUB}/.locks/models--Systran--faster-whisper-small",
        f"{HUB}/models--Qwen--Qwen2.5-1.5B-Instruct-GGUF",
        f"{HUB}/models--Systran--faster-whisper-small",
        f"{HUB}/models--someone--another-apps-model",
        ".config", ".config/autostart", ".config/tuxtalk",
        ".config/tuxtalk/config.toml", ".config/tuxtalk/custom_words.txt",
        ".local", ".local/share", ".local/share/TuxTalk",
        ".local/share/TuxTalk/recent-transcripts.json", ".local/share/TuxTalk/stats.json",
        ".local/share/applications", ".local/share/icons", ".local/share/icons/hicolor",
        ".local/share/icons/hicolor/256x256", ".local/share/icons/hicolor/256x256/apps",
        "Documents", "Documents/TuxTalk-settings-2026-10-20-0900.zip"])


def test_shared_models_go_when_asked_but_only_the_ones_tuxtalk_offers(home):
    """The Hugging Face cache is shared: an older faster-whisper model
    TuxTalk never offered may be another app's (review of 0.17)."""
    (home / HUB / "models--Systran--faster-whisper-large-v2").mkdir()
    uninstall.remove_files(_find(home), delete_personal=False, delete_shared=True)
    assert sorted(p.name for p in (home / HUB).iterdir()) == [
        "models--Systran--faster-whisper-large-v2", "models--someone--another-apps-model"]


def test_the_shared_models_box_says_what_is_there_and_where(home):
    plan = _find(home)
    assert uninstall.shared_text(plan, 600_000_000).startswith(
        f"Speech models and the AI model, 600 MB, in ~/{HUB}.")
    uninstall.remove_files(plan, delete_personal=False, delete_shared=True)
    assert _find(home).shared == []         # so the question has no box
    kept = uninstall.done_text(plan, delete_personal=False, delete_shared=False,
                               result=uninstall.Result())
    assert f"shared download folder are kept in <tt>~/{HUB}</tt>" in kept


def test_asked_to_it_leaves_nothing_of_tuxtalk_but_the_saved_backup(home):
    plan = _find(home)
    uninstall.remove_files(plan, delete_personal=True, delete_shared=True)
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
    uninstall.remove_files(plan, delete_personal=False, delete_shared=False)
    assert sorted(p.name for p in big_disk.iterdir()) == ["recent-transcripts.json", "stats.json"]
    uninstall.remove_files(_find(home), delete_personal=True, delete_shared=False)
    assert not os.path.lexists(data) and not big_disk.exists()


def test_a_linked_settings_folder_loses_only_tuxtalks_files(home, tmp_path):
    """Settings kept in a synced folder through a link: the folder holds other
    things too, and only what TuxTalk put there may go (review of 0.17)."""
    config = home / ".config/tuxtalk"
    synced = tmp_path / "Sync/dotfiles"
    synced.mkdir(parents=True)
    for name in ("config.toml", "config.toml.bak", "custom_words.txt", "tuxtalk.log.old"):
        (synced / name).write_text("ours")
    (synced / "backups").mkdir()
    (synced / "backups.photos").mkdir()
    (synced / "backups.photos/beach.jpg").write_text("someone else's")
    (synced / "notes.md").write_text("someone else's")
    (synced / "zshrc").write_text("someone else's")
    for path in config.iterdir():
        path.unlink()
    config.rmdir()
    config.symlink_to(synced)
    uninstall.remove_files(_find(home), delete_personal=True, delete_shared=False)
    assert not os.path.lexists(config)
    assert sorted(p.name for p in synced.iterdir()) == ["backups.photos", "notes.md", "zshrc"]
    assert (synced / "backups.photos/beach.jpg").exists()


def test_a_moved_data_folder_keeps_what_isnt_tuxtalks(home, tmp_path):
    data = home / ".local/share/TuxTalk"
    big_disk = tmp_path / "bigdisk/Models"
    big_disk.parent.mkdir()
    data.rename(big_disk)
    data.symlink_to(big_disk)
    (big_disk / "my-own-model.gguf").write_text("someone else's")
    uninstall.remove_files(_find(home), delete_personal=True, delete_shared=False)
    assert not os.path.lexists(data)
    assert [p.name for p in big_disk.iterdir()] == ["my-own-model.gguf"]


def test_a_link_inside_the_settings_folder_is_removed_not_followed(home, tmp_path):
    elsewhere = tmp_path / "Dropbox/backups"
    elsewhere.mkdir(parents=True)
    (elsewhere / "TuxTalk-settings.zip").write_text("a backup")
    (home / ".config/tuxtalk/backups").symlink_to(elsewhere)
    uninstall.remove_files(_find(home), delete_personal=True, delete_shared=False)
    assert not (home / ".config/tuxtalk").exists()
    assert [p.name for p in elsewhere.iterdir()] == ["TuxTalk-settings.zip"]


def test_the_running_appimage_goes_but_the_aur_packages_copy_is_pacmans(home, tmp_path):
    downloaded = home / "Downloads/TuxTalk-v0.17.0-x86_64.AppImage"
    downloaded.parent.mkdir()
    downloaded.write_text("program")
    assert downloaded in _find(home, appimage=str(downloaded)).leftovers
    assert downloaded not in _find(home, "aur", appimage=str(downloaded)).leftovers


def test_the_downloaded_appimage_in_appimages_goes_after_a_login_start(home):
    """Started at login, TuxTalk runs from the copy setup made, so the file
    the user downloaded into ~/AppImages was left behind (Zorin VM,
    2026-10-20). Other apps' AppImages stay."""
    apps = home / "AppImages"
    for name in ("TuxTalk-v0.17.0-x86_64.AppImage", "TalkType-v0.14.6-x86_64.AppImage",
                 "BambuStudio.AppImage"):
        (apps / name).write_text("program")
    plan = _find(home, appimage=str(apps / "TuxTalk.AppImage"))
    uninstall.remove_files(plan, delete_personal=False, delete_shared=False)
    assert sorted(p.name for p in apps.iterdir()) == ["BambuStudio.AppImage"]


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
    names = set()
    for source in (ROOT / "src/tuxtalk").glob("*.py"):
        names |= set(re.findall(r'get_data_dir\(\),\s*"([^"]+)"', source.read_text()))
    assert names, "the pattern no longer finds the data folder's files"
    known = set(uninstall.DOWNLOADED_DATA) | set(uninstall.PERSONAL_DATA)
    assert names <= known, names - known


def test_every_file_in_the_settings_folder_is_known_by_name():
    """A linked settings folder loses only the names in CONFIG_NAMES, so a new
    file TuxTalk writes there has to be added to them."""
    names = set()
    for source in (ROOT / "src/tuxtalk").glob("*.py"):
        names |= set(re.findall(r'dirname\((?:config\.)?CONFIG_PATH\),\s*"([^"]+)"',
                                source.read_text()))
    assert names, "the pattern no longer finds the settings folder's files"
    assert names <= set(uninstall.CONFIG_NAMES), names - set(uninstall.CONFIG_NAMES)


def test_the_hugging_face_cache_follows_its_own_settings(tmp_path):
    home = tmp_path
    assert uninstall.hf_hub_cache(home, {}) == home / ".cache/huggingface/hub"
    assert uninstall.hf_hub_cache(home, {"XDG_CACHE_HOME": "/c"}) == pathlib.Path("/c/huggingface/hub")
    assert uninstall.hf_hub_cache(home, {"HF_HOME": "/h", "XDG_CACHE_HOME": "/c"}) == pathlib.Path("/h/hub")
    assert uninstall.hf_hub_cache(home, {"HF_HUB_CACHE": "/x", "HF_HOME": "/h"}) == pathlib.Path("/x")
    assert uninstall.hf_hub_cache(home, {"HUGGINGFACE_HUB_CACHE": "/old", "HF_HOME": "/h"}) \
        == pathlib.Path("/old")
    assert uninstall.hf_hub_cache(home, {"HF_HUB_CACHE": "/x", "HUGGINGFACE_HUB_CACHE": "/old"}) \
        == pathlib.Path("/x")


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
    assert 'gpasswd -d "$user" input' in script
    assert f"echo {secure_input.STILL_IN_GROUP}" in script
    assert subprocess.run(["bash", "-n"], input=script, text=True).returncode == 0


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
    pathlib.Path(uinput_helper.UDEV_RULE_PATH).write_text("")     # 0.15's rule, no helper
    text = uninstall.confirm_text(_find(home), 1)
    assert "the permission it set up to type" in text and "hotkey helper" not in text
    pathlib.Path(secure_input.UNIT_PATH).write_text("")
    (home / ".local/share/gnome-shell/extensions/talktype@ronb1964.github.io").mkdir(parents=True)
    text = uninstall.confirm_text(_find(home, "deb"), 1)
    assert "the tuxtalk package" in text and "hotkey helper" in text and "GNOME extension" in text


def test_the_closing_message_says_how_to_finish_a_refused_package(home):
    result = uninstall.Result(package_failed=True)
    text = uninstall.done_text(_find(home, "rpm"), delete_personal=True, delete_shared=True,
                               result=result)
    assert "sudo dnf remove tuxtalk" in text
    assert "Log out" not in text
    assert uninstall.done_heading(result) == "TuxTalk couldn't remove everything"


def test_what_the_root_script_couldnt_remove_is_named_not_hidden():
    """The closing message said "TuxTalk is uninstalled" whatever the root
    steps did, and "log out to leave the input group" when gpasswd had
    failed (review of 0.17)."""
    report = "\n".join([f"{secure_input.NOT_REMOVED} helper", secure_input.STILL_IN_GROUP])
    result = uninstall.root_result(report, leave_group=True)
    assert result.not_removed == ["the hotkey helper (tuxtalk-hotkeys.service)",
                                  "your place in the 'input' group"]
    assert not result.left_group and not result.complete
    assert uninstall.root_result("", leave_group=True).left_group
    assert uninstall.root_result("", leave_group=True).complete


def test_the_root_script_reports_a_helper_still_there(tmp_path, monkeypatch):
    """Run for real against made-up paths, with an rm that fails."""
    for name in ("UNIT_PATH", "HELPER_PATH", "UINPUT_RULE_PATH"):
        monkeypatch.setattr(secure_input, name, str(tmp_path / name))
        (tmp_path / name).write_text("")
    monkeypatch.setattr(uinput_helper, "UDEV_RULE_PATH", str(tmp_path / "old-rule"))
    fake = tmp_path / "bin"
    fake.mkdir()
    for name, body in (("systemctl", "exit 3"), ("udevadm", "exit 0"), ("rmdir", "exit 0")):
        (fake / name).write_text(f"#!/bin/sh\n{body}\n")
        (fake / name).chmod(0o755)
    env = {"PATH": f"{fake}:/usr/bin:/bin"}
    (fake / "rm").write_text("#!/bin/sh\nexit 1\n")
    (fake / "rm").chmod(0o755)
    ran = subprocess.run(["bash", "-c", secure_input.uninstall_lines()], capture_output=True,
                         text=True, env=env)
    assert ran.stdout.split("\n")[:2] == [f"{secure_input.NOT_REMOVED} helper",
                                         f"{secure_input.NOT_REMOVED} rule"]
    (fake / "rm").unlink()
    ran = subprocess.run(["bash", "-c", secure_input.uninstall_lines()], capture_output=True,
                         text=True, env=env)
    assert secure_input.NOT_REMOVED not in ran.stdout


def test_files_that_wont_go_are_listed_in_the_closing_message(home):
    stuck = home / ".local/share/TuxTalk/cuda"
    (stuck / "lib").chmod(0o500)        # its file can't be deleted
    try:
        failed = uninstall.remove_files(_find(home), delete_personal=False, delete_shared=False)
    finally:
        (stuck / "lib").chmod(0o700)
    assert stuck in failed
    result = uninstall.Result(not_removed=[uninstall._shown(stuck, home)])
    text = uninstall.done_text(_find(home), delete_personal=False, delete_shared=False,
                               result=result)
    assert "These are still there:\n•  ~/.local/share/TuxTalk/cuda" in text
    assert uninstall.done_heading(result) == "TuxTalk couldn't remove everything"


def test_a_file_that_went_on_the_second_try_isnt_reported(home, monkeypatch):
    """A download that wouldn't go at first can go with its folder when the
    settings are deleted too; the closing message must not list it."""
    real, tries = uninstall._remove, []

    def flaky(path):
        if path.name == "cuda" and not tries:
            tries.append(path)
            return False
        return real(path)
    monkeypatch.setattr(uninstall, "_remove", flaky)
    assert uninstall.remove_files(_find(home), delete_personal=True, delete_shared=False) == []
    assert tries


def test_an_extension_that_stays_is_named(home, monkeypatch):
    ext = home / ".local/share/gnome-shell/extensions/talktype@ronb1964.github.io"
    ext.mkdir(parents=True)
    monkeypatch.setattr(uninstall.gnome_keybindings, "restore_left_over", lambda: None)
    monkeypatch.setattr(uninstall.kwin_hotkeys, "forget_our_components", lambda: None)
    monkeypatch.setattr(uninstall.extension_helper, "uninstall_extension", lambda: False)
    assert uninstall.undo_desktop_changes(_find(home)) == [
        "the GNOME extension (~/.local/share/gnome-shell/extensions/talktype@ronb1964.github.io)"]
    monkeypatch.setattr(uninstall.extension_helper, "uninstall_extension",
                        lambda: ext.rmdir() or True)
    assert uninstall.undo_desktop_changes(_find(home)) == []


def test_a_timed_out_password_prompt_doesnt_claim_nothing_changed(home, monkeypatch):
    told = []
    monkeypatch.setattr(uninstall.secure_input, "_run_as_root",
                        lambda script, what: (False, secure_input.TIMED_OUT))
    monkeypatch.setattr(uninstall, "_tell", lambda kind, heading, body, **k: told.append(body))
    assert uninstall._remove_as_root(_find(home), leave_group=False) is None
    assert "may already be gone" in told[0] and "Nothing was removed" not in told[0]


def test_an_error_partway_still_ends_with_a_message_and_quits(home, monkeypatch):
    """With the tray's parts already stopped, going back to it would leave a
    half-shut TuxTalk (review of 0.17)."""
    told = []
    monkeypatch.setattr(uninstall.update_checker, "get_install_type", lambda: "appimage")
    monkeypatch.setattr(uninstall.update_checker, "get_running_appimage_path", lambda: None)
    plan = _find(home)
    monkeypatch.setattr(uninstall, "find", lambda *a, **k: plan)
    monkeypatch.setattr(uninstall, "_ask", lambda plan: (False, False, False))
    monkeypatch.setattr(uninstall, "_working_window", lambda: types.SimpleNamespace(destroy=lambda: None))
    monkeypatch.setattr(uninstall, "_tell", lambda kind, heading, body, **k: told.append((heading, body)))

    def stop(plan, stop_tray_parts):
        stop_tray_parts()
        raise RuntimeError("D-Bus went away")
    monkeypatch.setattr(uninstall, "stop_tuxtalk", stop)
    stopped = []
    assert uninstall.run(stop_tray_parts=lambda: stopped.append(1)) is True
    assert stopped == [1]
    heading, body = told[0]
    assert heading == "TuxTalk couldn't remove everything"
    assert "stopped partway (D-Bus went away)" in body


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


def test_logging_after_the_settings_folder_is_deleted_neither_fails_nor_recreates_it(tmp_path):
    """Uninstalling with the settings deletes the log's folder; the next log
    line crashed the uninstall before its closing message (VM test,
    2026-10-20). Run apart, so this process's own logging is untouched."""
    import sys
    log_dir = tmp_path / "config"
    script = (
        "import logging, shutil\n"
        "from tuxtalk.logger import setup_logger, stop_file_logging\n"
        "log = setup_logger('tuxtalk.anything')\n"
        "log.info('before')\n"
        "stop_file_logging()\n"
        f"shutil.rmtree({str(log_dir)!r})\n"
        "log.info('after')\n"
        "setup_logger('tuxtalk.later').info('a logger set up afterwards')\n"
        "logging.getLogger('tuxtalk').warning('the package logger')\n")
    ran = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                         env={**os.environ, "TUXTALK_LOG_DIR": str(log_dir)})
    assert ran.returncode == 0, ran.stderr
    assert not log_dir.exists()


def test_in_the_development_version_the_button_only_explains(monkeypatch):
    """Ron sees the button in his dev copy too; pressing it there must never
    take away the hotkey helper and models his dev copy runs on."""
    told = []
    monkeypatch.setattr(uninstall.update_checker, "get_install_type", lambda: "dev")
    monkeypatch.setattr(uninstall, "_tell", lambda *a, **k: told.append(a[1]))
    monkeypatch.setattr(uninstall, "find", lambda *a, **k: pytest.fail("looked for things to remove"))
    assert uninstall.run() is False
    assert told == ["Not for this copy of TuxTalk"]


def test_a_tuxtalk_that_cant_uninstall_says_so():
    """The dictation service stands in for a crashed tray but can't
    uninstall: it used to accept the call and do nothing, and Preferences and
    tuxtalk --uninstall took that as done (review of 0.17)."""
    import types
    import dbus
    from tuxtalk.dbus_service import TuxTalkDBusService
    svc = TuxTalkDBusService.__new__(TuxTalkDBusService)
    svc.app = types.SimpleNamespace()
    with pytest.raises(dbus.exceptions.DBusException) as refused:
        svc.Uninstall()
    assert refused.value.get_dbus_name() == "org.freedesktop.DBus.Error.UnknownMethod"


def test_the_command_line_uninstalls_itself_when_the_running_one_cant(monkeypatch):
    from tuxtalk import tray
    monkeypatch.setattr(control, "open_in_running", lambda name, tray_starting: False)
    ran = []
    monkeypatch.setattr(uninstall, "run", lambda: ran.append(1) or True)
    with pytest.raises(SystemExit) as finished:
        tray._open_from_command_line("uninstall")
    assert ran == [1] and finished.value.code == 0

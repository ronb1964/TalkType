"""Uninstall TuxTalk: Preferences -> Updates & Backup -> Uninstall TuxTalk...,
or `tuxtalk --uninstall`.

Removing the package or deleting the AppImage takes away only the program.
Running it sets up much more: the hotkey helper service and udev rules (as
root), the input group on older setups, a launcher, an icon and start at
login, the GNOME extension, KDE shortcuts, and gigabytes of downloads
(speech models, the Vulkan and AI engines, CUDA libraries). A Zorin OS user
removed the .deb in October 2026 and found all of it still there.

This takes all of it away, with one password prompt. Downloads always go;
settings, Your Words, snippets and stats only when asked, so a reinstall
can pick up where it left off. Backup files the user saved elsewhere are
theirs and stay.

It runs in the tray's process when TuxTalk is running: an AppImage's files
vanish when its first process (the tray) exits, and this needs them to the
end. Removing the .deb or .rpm deletes this very code mid-run, so every
module it uses afterwards is imported here, up front.
"""
import grp
import os
import pwd
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import (ai_cleanup, config, desktop_detect, extension_helper,  # noqa: E402
               file_transcribe, gnome_keybindings, kwin_hotkeys,
               parakeet_engine, secure_input, service_launcher, uinput_helper,
               update_checker, whisper_vulkan)
from .logger import setup_logger, stop_file_logging  # noqa: E402
from .ui_style import message_dialog  # noqa: E402

logger = setup_logger(__name__)

# The files in the data folder that are the user's own: kept unless they
# ask for them to go. Everything else there is downloaded or rebuilt by
# itself (tests/test_uninstall.py makes every name in the code choose).
PERSONAL_DATA = ("stats.json", "stats.json.bak", file_transcribe.RECENT_FILE)

# Each Hugging Face repository TuxTalk downloads from, as the cache names
# its folder. faster-whisper also maps the .en and older large names onto
# Systran's repos, hence the pattern.
HF_REPOS = ("models--Systran--faster-whisper-*",
            *(f"models--{repo.replace('/', '--')}" for repo in (
                parakeet_engine.V3_REPO, whisper_vulkan.MODEL_REPO,
                *whisper_vulkan.MODEL_REPOS.values(), ai_cleanup.MODEL_REPO)))

# The runtime folder's files that hold dictated text: Recent Dictations and
# Fix a Word's last dictation. Logging out empties the folder anyway; its
# lock files stay, since a development copy running beside this one uses
# the same names.
RUNTIME_FILES = ("talktype-history.json", "tuxtalk-fix-word.json")

ICON_SIZES = ("256x256", "128x128", "64x64", "48x48", "32x32")

# The packages, by how TuxTalk was installed.
PACKAGES = {"deb": "tuxtalk", "rpm": "tuxtalk", "aur": "tuxtalk-appimage"}

FEEDBACK_URL = "https://github.com/ronb1964/TuxTalk/discussions"


@dataclass
class Plan:
    """What there is to remove on this computer."""
    home: Path
    install_type: str
    downloads: list = field(default_factory=list)     # always removed
    leftovers: list = field(default_factory=list)     # launchers, autostart, program
    personal: list = field(default_factory=list)      # removed only when asked
    runtime: list = field(default_factory=list)
    hub: Path = None                 # Hugging Face's model cache
    helper: bool = False             # the hotkey helper is installed
    typing_rule: bool = False        # a udev rule lets TuxTalk type (either version)
    input_group: bool = False        # TuxTalk's old setup put the user in it
    ydotoold_unit: Path = None       # TuxTalk's systemd user unit, if any
    extension: bool = False

    @property
    def package(self):
        return PACKAGES.get(self.install_type)

    @property
    def needs_root(self):
        return self.helper or self.typing_rule or self.input_group or self.package is not None


def hf_hub_cache(home, environ=os.environ):
    """Where Hugging Face keeps its models, by its own rules."""
    if environ.get("HF_HUB_CACHE"):
        return Path(environ["HF_HUB_CACHE"])
    if environ.get("HF_HOME"):
        return Path(environ["HF_HOME"]) / "hub"
    cache = Path(environ["XDG_CACHE_HOME"]) if environ.get("XDG_CACHE_HOME") else home / ".cache"
    return cache / "huggingface" / "hub"


def _ours(path):
    """A systemd user unit TuxTalk wrote (uinput_helper's template); the name
    ydotoold.service is generic, so the description has to say so."""
    try:
        text = path.read_text()
    except OSError:
        return False
    return "(TuxTalk keystroke injection)" in text or "(TalkType keystroke injection)" in text


def _in_input_group():
    """In the group now, or added and not logged in again since."""
    try:
        group = grp.getgrnam("input")
    except KeyError:
        return False
    return group.gr_gid in os.getgroups() or pwd.getpwuid(os.getuid()).pw_name in group.gr_mem


def find(home, install_type, environ=os.environ, appimage=None):
    """The Plan for *home*: only what exists. *appimage* is the running
    AppImage's path, if any."""
    plan = Plan(home=home, install_type=install_type)
    config_dir = home / ".config" / config.CONFIG_DIR
    data_dir = home / ".local" / "share" / config.DATA_DIR

    def exists(path):
        return os.path.lexists(path)

    if data_dir.is_dir():
        for entry in sorted(data_dir.iterdir()):
            (plan.personal if entry.name in PERSONAL_DATA else plan.downloads).append(entry)
    plan.hub = hf_hub_cache(home, environ)
    for pattern in HF_REPOS:
        plan.downloads += (sorted(plan.hub.glob(pattern))
                           + sorted((plan.hub / ".locks").glob(pattern)))

    apps = home / "AppImages"
    # The versioned files too: started at login, TuxTalk runs from the copy
    # setup made, and the one the user downloaded here would stay behind.
    candidates = [apps / "TuxTalk.AppImage", apps / "TalkType.AppImage",
                  *sorted(apps.glob("TuxTalk-*.AppImage")),
                  *sorted(apps.glob("TalkType-*.AppImage")),
                  apps / ".tuxtalk_just_updated", apps / ".talktype_just_updated",
                  *sorted(apps.glob(".TuxTalk.AppImage.*.part"))]
    if appimage and install_type == "appimage":
        candidates.insert(0, Path(appimage))
    for name in ("tuxtalk.desktop", "talktype.desktop"):
        candidates += [home / ".config" / "autostart" / name,
                       home / ".local" / "share" / "applications" / name]
    icons = home / ".local" / "share" / "icons" / "hicolor"
    for size in ICON_SIZES:
        candidates += [icons / size / "apps" / "tuxtalk.png", icons / size / "apps" / "talktype.png"]
    candidates.append(icons / "scalable" / "apps" / f"{config.APP_ID}.svg")
    for path in candidates:
        if exists(path) and path not in plan.leftovers:
            plan.leftovers.append(path)

    if config_dir.is_dir() or config_dir.is_symlink():
        plan.personal.insert(0, config_dir)
    # The names from before the 0.15.0 rename: links to the folders above, or
    # the real folders behind them when the rename couldn't move them.
    for old in (home / ".config" / "talktype", home / ".local" / "share" / "TalkType"):
        if exists(old):
            plan.personal.append(old)
    if data_dir.is_dir():
        plan.personal.append(data_dir)      # the folder itself, last

    runtime = Path(environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
    plan.runtime = [runtime / name for name in RUNTIME_FILES if exists(runtime / name)]

    unit = home / ".config" / "systemd" / "user" / "ydotoold.service"
    if _ours(unit):
        plan.ydotoold_unit = unit
    plan.extension = exists(Path(desktop_detect.get_extension_dir()) / extension_helper.EXTENSION_UUID)
    plan.helper = any(os.path.exists(p) for p in (secure_input.UNIT_PATH, secure_input.HELPER_PATH))
    plan.typing_rule = any(os.path.exists(p) for p in (secure_input.UINPUT_RULE_PATH,
                                                       uinput_helper.UDEV_RULE_PATH))
    # Only the old setup's own rule says TuxTalk put the user in the group.
    plan.input_group = os.path.exists(uinput_helper.UDEV_RULE_PATH) and _in_input_group()
    return plan


def download_size(plan):
    """Bytes the downloads take on disk (each file counted once)."""
    total, seen = 0, set()
    for top in plan.downloads:
        for root, _dirs, files in os.walk(top):
            for name in files:
                try:
                    st = os.lstat(os.path.join(root, name))
                except OSError:
                    continue
                if (st.st_dev, st.st_ino) not in seen:
                    seen.add((st.st_dev, st.st_ino))
                    total += st.st_blocks * 512
    return total


def _package_lines(plan):
    """Shell lines removing TuxTalk's package; on failure they print
    PACKAGE_NOT_REMOVED and the package manager's last lines."""
    name = plan.package
    if plan.install_type == "deb":
        command = f"DEBIAN_FRONTEND=noninteractive apt-get remove -y {name}"
    elif plan.install_type == "rpm":
        command = (f"if command -v dnf >/dev/null; then dnf remove -y {name}; "
                   f"elif command -v zypper >/dev/null; then zypper --non-interactive remove {name}; "
                   f"else rpm -e {name}; fi")
    else:
        command = f"pacman -R --noconfirm {name}"
    return (f'if ! out=$( {{ {command}; }} 2>&1 ); then\n'
            f'    echo {secure_input.PACKAGE_NOT_REMOVED}\n'
            f'    printf "%s\\n" "$out" | tail -n 3\n'
            f'fi\n')


def root_script(plan, leave_group):
    """What pkexec runs as root: the hotkey helper and typing rules, the
    input group when the user said so, then the package. Every step runs
    even if one before it failed."""
    lines = "set -uo pipefail\n"
    if leave_group:
        lines += 'gpasswd -d "$(id -nu "${PKEXEC_UID:?}")" input || true\n'
    lines += secure_input.uninstall_lines()
    if plan.package:
        lines += _package_lines(plan)
    return lines + "exit 0\n"


def _remove(path):
    """Remove a file, a link (never what it points at), or a folder."""
    try:
        if path.is_symlink() or not path.is_dir():
            path.unlink(missing_ok=True)
        else:
            shutil.rmtree(path)
    except OSError as e:
        logger.warning(f"Could not remove {path}: {e}")


def _empty(folder):
    """Remove what's in *folder*, following a link to it (a user who moved
    the models to a bigger disk), then the folder, or the link and the
    folder it led to."""
    target = folder.resolve() if folder.is_symlink() else None
    if folder.is_dir():
        for entry in folder.iterdir():
            _remove(entry)
    _remove(folder)
    if target is not None:
        try:
            target.rmdir()
        except OSError:
            pass        # gone already, or something else is in it


def remove_files(plan, delete_personal):
    """Delete the files the plan lists. Only files: the desktop's own
    settings are undone by undo_desktop_changes() first."""
    for path in plan.downloads + plan.leftovers + plan.runtime:
        _remove(path)
    if delete_personal:
        for path in plan.personal:
            if path.is_dir():
                _empty(path)
            else:
                _remove(path)
    # Folders TuxTalk made and nothing else uses: gone once empty.
    folders = [plan.home / "AppImages", plan.hub / ".locks", plan.hub]
    if plan.hub.parent.name == "huggingface":
        folders.append(plan.hub.parent)
    for folder in folders:
        try:
            folder.rmdir()
        except OSError:
            pass        # not empty, or not there
    if plan.ydotoold_unit is not None:
        _remove(plan.ydotoold_unit)


def _tuxtalk_pids(data_dir):
    """This user's other TuxTalk processes: its Python modules (service,
    Preferences, Transcribe a File, an old TalkType) and the engines it
    downloaded into *data_dir*."""
    me, uid = os.getpid(), os.getuid()
    pids = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) == me:
            continue
        pid = int(entry)
        try:
            if os.stat(f"/proc/{pid}").st_uid != uid:
                continue
            argv = service_launcher._read_argv(pid) or []
            exe = os.path.realpath(f"/proc/{pid}/exe")
        except OSError:
            continue
        module = any(a == "-m" and b.startswith(("tuxtalk.", "talktype."))
                     for a, b in zip(argv, argv[1:]))
        if (module or exe.startswith(str(data_dir) + os.sep)) and not _is_dev(pid):
            pids.append(pid)
    return pids


def _is_dev(pid):
    """A development copy (DEV_MODE=1) has its own folders: not ours to stop."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            return b"DEV_MODE=1" in f.read().split(b"\0")
    except OSError:
        return False


def stop_tuxtalk(plan, stop_tray_parts=None):
    """Stop everything TuxTalk runs, so nothing writes a file back after
    it's deleted. *stop_tray_parts* is the tray's own shutdown when this runs
    inside it."""
    if stop_tray_parts is not None:
        stop_tray_parts()
    service_launcher.stop_dictation_service()      # also lets KDE have the hotkeys back
    uinput_helper.stop_ydotoold_we_started()
    data_dir = (plan.home / ".local" / "share" / config.DATA_DIR).resolve()
    pids = _tuxtalk_pids(data_dir)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.monotonic() + 3
    while pids and time.monotonic() < deadline:
        time.sleep(0.1)
        pids = [pid for pid in pids if os.path.exists(f"/proc/{pid}")]
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    if plan.ydotoold_unit is not None:
        for args in (["disable", "--now", "ydotoold.service"], ["daemon-reload"]):
            subprocess.run(["systemctl", "--user", *args], capture_output=True, timeout=15)


def undo_desktop_changes(plan):
    """Put the desktop back as it was: Alt+F7/Alt+F8 on GNOME if the hotkey
    test was cut short, the GNOME extension, KDE's shortcut entries. Runs
    after stop_tuxtalk() and before the files go (the keybindings' backup
    is one of them)."""
    gnome_keybindings.restore_left_over()
    if plan.extension or desktop_detect.is_gnome():
        extension_helper.uninstall_extension()
    kwin_hotkeys.forget_our_components()


def _refresh_menus():
    """Let the app menus forget the launcher; quiet when a tool is missing."""
    data = Path.home() / ".local" / "share"
    for command in (["update-desktop-database", "-q", str(data / "applications")],
                    ["gtk-update-icon-cache", "-q", "-f", "-t", str(data / "icons" / "hicolor")],
                    ["kbuildsycoca6"], ["kbuildsycoca5"]):
        try:
            subprocess.run(command, capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass


# ---------------------------------------------------------------------------
# The dialogs


def _size_text(size):
    """Decimal units, as every download size in TuxTalk is shown."""
    if size >= 1000 ** 3:
        return f"{size / 1000 ** 3:.1f} GB"
    return f"{max(1, round(size / 1000 ** 2))} MB"


def confirm_text(plan, size):
    """The bullet lines of the question: what will go, as found here."""
    program = {
        "appimage": "TuxTalk itself (its AppImage)",
        "deb": "TuxTalk itself (the tuxtalk package)",
        "rpm": "TuxTalk itself (the tuxtalk package)",
        "aur": "TuxTalk itself (the tuxtalk-appimage package)",
    }.get(plan.install_type)
    lines = [program] if program else []
    if plan.helper:
        lines.append("its hotkey helper and the permission to type into other apps")
    elif plan.typing_rule:
        lines.append("the permission it set up to type into other apps")
    if plan.downloads:
        lines.append(f"the speech models, engines and libraries it downloaded ({_size_text(size)})")
    lines.append("starting at login, its menu entry and the GNOME extension" if plan.extension
                 else "starting at login and its menu entry")
    return "\n".join(f"•  {line}" for line in lines)


def _wait_for(work):
    """Run *work* on a thread while the window keeps drawing; its result."""
    result = {}
    loop = GLib.MainLoop()

    def run():
        try:
            result["value"] = work()
        except Exception as e:      # handed back to the caller below
            result["error"] = e
        GLib.idle_add(loop.quit)

    threading.Thread(target=run, daemon=True).start()
    loop.run()
    if "error" in result:
        raise result["error"]
    return result["value"]


def _ask(plan, size):
    """(delete_personal, leave_group), or None for Cancel."""
    dialog = message_dialog(message_type=Gtk.MessageType.QUESTION,
                            buttons=Gtk.ButtonsType.NONE, text="Uninstall TuxTalk?")
    text = ("This removes TuxTalk and everything it set up on this computer:\n\n"
            + confirm_text(plan, size))
    if plan.needs_root:
        text += "\n\nYou'll be asked for your password once."
    dialog.format_secondary_text(text)
    area = dialog.get_message_area()

    personal = Gtk.CheckButton(label="Also delete my settings, Your Words, snippets and stats")
    area.pack_start(personal, False, False, 0)
    note = Gtk.Label(xalign=0, label="Otherwise they stay, so installing TuxTalk again picks "
                                     "up where you left off. Backups you saved stay either way.")
    note.set_line_wrap(True)
    note.set_max_width_chars(60)
    note.get_style_context().add_class("dim-label")
    area.pack_start(note, False, False, 0)

    group = None
    if plan.input_group:
        group = Gtk.CheckButton(label="Take me out of the 'input' group")
        group.set_active(True)
        area.pack_start(group, False, False, 0)
        why = Gtk.Label(xalign=0, label="TuxTalk added you to it, which lets programs read the "
                                        "keyboard. Untick it if another program you use needs "
                                        "it, a key remapper for instance.")
        why.set_line_wrap(True)
        why.set_max_width_chars(60)
        why.get_style_context().add_class("dim-label")
        area.pack_start(why, False, False, 0)

    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    button = dialog.add_button("Uninstall", Gtk.ResponseType.OK)
    button.get_style_context().add_class("destructive-action")
    dialog.set_default_response(Gtk.ResponseType.CANCEL)
    dialog.set_position(Gtk.WindowPosition.CENTER)
    dialog.set_keep_above(True)
    area.show_all()
    answer = dialog.run()
    choice = (personal.get_active(), bool(group and group.get_active()))
    dialog.destroy()
    return choice if answer == Gtk.ResponseType.OK else None


def _working_window():
    """A small "Uninstalling TuxTalk..." window while the work runs."""
    window = Gtk.Window(title="TuxTalk")
    window.set_position(Gtk.WindowPosition.CENTER)
    window.set_resizable(False)
    window.set_deletable(False)
    window.set_keep_above(True)
    box = Gtk.Box(spacing=12)
    for side in ("top", "bottom", "start", "end"):
        getattr(box, f"set_margin_{side}")(20)
    spinner = Gtk.Spinner()
    spinner.start()
    box.pack_start(spinner, False, False, 0)
    box.pack_start(Gtk.Label(label="Uninstalling TuxTalk…"), False, False, 0)
    window.add(box)
    window.show_all()
    return window


def _tell(kind, heading, body, markup=False):
    dialog = message_dialog(message_type=kind, buttons=Gtk.ButtonsType.OK, text=heading)
    if markup:
        dialog.format_secondary_markup(body)
    else:
        dialog.format_secondary_text(body)
    dialog.set_position(Gtk.WindowPosition.CENTER)
    dialog.set_keep_above(True)
    dialog.run()
    dialog.destroy()


def done_text(plan, delete_personal, left_group, package_failed):
    """The closing message's body (Pango markup)."""
    parts = []
    if package_failed:
        command = {"deb": "sudo apt remove tuxtalk", "rpm": "sudo dnf remove tuxtalk",
                   "aur": "sudo pacman -R tuxtalk-appimage"}[plan.install_type]
        parts.append("Everything else is gone, but the package manager wouldn't remove "
                     "the program itself (it may be busy with an update). Remove it "
                     f"later with:\n<tt>{command}</tt>")
    elif plan.install_type == "package":
        parts.append("Remove the tuxtalk package with your package manager to finish.")
    logout = []
    if plan.extension:
        logout.append("GNOME shows the extension's menu until then")
    if left_group:
        logout.append("leaving the 'input' group takes effect then")
    if logout:
        parts.append("Log out and back in to finish: " + ", and ".join(logout) + ".")
    if not delete_personal and any(p.exists() for p in plan.personal):
        parts.append("Your settings, Your Words and snippets are kept in "
                     f"<tt>~/.config/{config.CONFIG_DIR}</tt>.")
    parts.append(f'If TuxTalk didn\'t work out for you, <a href="{FEEDBACK_URL}">tell us '
                 "why</a>. It helps.")
    return "\n\n".join(parts)


def run(stop_tray_parts=None):
    """Ask, then uninstall. True when TuxTalk was uninstalled and the caller
    should quit; False when nothing changed."""
    install_type = update_checker.get_install_type()
    if install_type in ("dev", "flatpak"):
        _tell(Gtk.MessageType.INFO, "Not for this copy of TuxTalk",
              "The development version runs from its source folder, and a Flatpak "
              "is removed with: flatpak uninstall --delete-data io.github.ronb1964.TuxTalk")
        return False
    plan = find(Path.home(), install_type, appimage=update_checker.get_running_appimage_path())
    choice = _ask(plan, download_size(plan))
    if choice is None:
        return False
    delete_personal, leave_group = choice
    logger.info(f"Uninstalling TuxTalk ({install_type}); settings "
                + ("deleted" if delete_personal else "kept"))

    window = _working_window()
    try:
        package_failed = False
        if plan.needs_root:
            ok, message = _wait_for(lambda: secure_input._run_as_root(
                root_script(plan, leave_group), "removed (uninstalling TuxTalk)"))
            if not ok:
                window.destroy()
                if message != "cancelled":
                    _tell(Gtk.MessageType.ERROR, "TuxTalk couldn't uninstall",
                          f"Nothing was removed.\n\n{message}")
                return False
            package_failed = message == secure_input.PACKAGE_NOT_REMOVED
        stop_tuxtalk(plan, stop_tray_parts)
        undo_desktop_changes(plan)
        # Looked for again: stopping may have written a file (the stats).
        again = find(Path.home(), install_type, appimage=update_checker.get_running_appimage_path())
        if delete_personal:
            logger.info("Uninstalled TuxTalk; deleting the settings and this log")
            stop_file_logging()         # its folder is about to go
        _wait_for(lambda: remove_files(again, delete_personal))
        _wait_for(_refresh_menus)
    finally:
        window.destroy()
    logger.info("Uninstalled TuxTalk")
    _tell(Gtk.MessageType.INFO, "TuxTalk is uninstalled",
          done_text(plan, delete_personal, leave_group, package_failed), markup=True)
    return True

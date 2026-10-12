"""Move a TalkType install's folders to their TuxTalk names (0.15.0 rename).

TalkType became TuxTalk because "TALKTYPE" is another company's registered
trademark for dictation software. Users must not notice beyond the new name:

Runs first in every entry point (tray, dictation service, Preferences), before
anything reads a path. Each old folder is renamed to its new name and replaced
by a symlink, so an old TalkType copy that is still installed keeps working on
the same settings and models. Nothing is ever deleted, copied or overwritten:
- both names exist   -> leave both, log it, use the new one
- other disk (EXDEV) -> point the NEW name at the old folder instead of moving
"""
import errno
import os

# Files TuxTalk creates on its own the moment it starts (the logger writes its
# log before anything else). A new folder holding only these is not "in use".
_AUTO_CREATED = {"tuxtalk.log", "tuxtalk.log.old"}


def _only_auto_created(folder):
    try:
        names = os.listdir(folder)
    except OSError:
        return False
    return all(n in _AUTO_CREATED and os.path.isfile(os.path.join(folder, n)) for n in names)


def PAIRS(dev=False):
    """(old, new) folder paths relative to the home folder."""
    s = "-dev" if dev else ""
    return [(f".config/talktype{s}", f".config/tuxtalk{s}"),
            (f".local/share/TalkType{s}", f".local/share/TuxTalk{s}")]


def migrate(home=None, dev=False):
    """Move the old folders; return one line per thing done, for the log.

    Never raises: a failure becomes a line, and startup carries on.
    """
    home = home or os.path.expanduser("~")
    done = []
    for old_rel, new_rel in PAIRS(dev):
        old, new = os.path.join(home, old_rel), os.path.join(home, new_rel)
        if os.path.islink(old) or not os.path.isdir(old):
            continue                      # nothing old, or already migrated
        if (os.path.isdir(new) and not os.path.islink(new) and _only_auto_created(new)):
            # Fold the fresh log into the old folder, so the move below keeps it.
            for n in os.listdir(new):
                if not os.path.exists(os.path.join(old, n)):
                    os.rename(os.path.join(new, n), os.path.join(old, n))
            try:
                os.rmdir(new)
            except OSError:
                pass
        if os.path.lexists(new):
            done.append(f"{old_rel} and {new_rel} both exist; "
                        f"using {new_rel}, left {old_rel} alone")
            continue
        try:
            os.makedirs(os.path.dirname(new), exist_ok=True)
            os.rename(old, new)
            os.symlink(new, old)
            done.append(f"moved {old_rel} to {new_rel}")
        except OSError as e:
            if e.errno != errno.EXDEV:
                done.append(f"could not move {old_rel}: {e}")
                continue
            # A rename can't cross disks, and copying gigabytes of models at
            # startup is not acceptable. Let the new name lead to the old folder.
            try:
                os.symlink(old, new)
                done.append(f"{old_rel} is on another disk; {new_rel} now points to it")
            except OSError as e2:
                done.append(f"could not link {new_rel}: {e2}")
    return done


def run_at_startup(environ=None, home=None):
    """The package-import entry point. Off in the test suite
    (TUXTALK_NO_MIGRATE) and in the Flatpak, whose folders live in its own
    sandbox and never had the old names on the host."""
    environ = os.environ if environ is None else environ
    if environ.get("TUXTALK_NO_MIGRATE") or environ.get("FLATPAK_ID"):
        return []
    try:
        return migrate(home=home, dev=environ.get("DEV_MODE") == "1")
    except Exception as e:      # never stop the app from starting
        return [f"rename migration failed: {e}"]


def _rewrite_entry(text, dev):
    """A TalkType .desktop entry with TuxTalk's name, AppImage and description.
    Everything else (launch-at-login on or off above all) is kept as it was."""
    from .autostart import AUTOSTART_COMMENT, AUTOSTART_COMMENT_DEV, _OLD_COMMENTS
    out = []
    for line in text.splitlines(keepends=True):
        if line.startswith("Name=TalkType"):
            line = "Name=TuxTalk" + line[len("Name=TalkType"):]
        elif line.startswith("Exec="):
            line = line.replace("/TalkType.AppImage", "/TuxTalk.AppImage")
        elif line.rstrip("\n") in (f"Comment={c}" for c in _OLD_COMMENTS):
            line = f"Comment={AUTOSTART_COMMENT_DEV if dev else AUTOSTART_COMMENT}\n"
        out.append(line)
    return "".join(out)


def adopt_old_install(home=None, dev=False):
    """Move an installed TalkType's AppImage, menu launcher and launch-at-login
    entry to TuxTalk's names. Called by the tray on start; returns log lines.

    A 0.14.x updater saves the new version as ~/AppImages/TalkType.AppImage and
    restarts it, so this is how an updated install ends up fully renamed. The
    AppImage is renamed (safe while it runs) and a symlink keeps the old path
    working; an existing TuxTalk.AppImage is never overwritten. The .desktop
    entries are rewritten under the new name and the old ones removed, so the
    menu never lists both and login never starts both.
    """
    home = home or os.path.expanduser("~")
    done = []
    if not dev:
        old = os.path.join(home, "AppImages", "TalkType.AppImage")
        new = os.path.join(home, "AppImages", "TuxTalk.AppImage")
        if os.path.isfile(old) and not os.path.islink(old) and not os.path.lexists(new):
            try:
                os.rename(old, new)
                os.symlink(new, old)
                done.append("renamed ~/AppImages/TalkType.AppImage to TuxTalk.AppImage")
            except OSError as e:
                done.append(f"could not rename the AppImage: {e}")
    suffix = "-dev" if dev else ""
    for folder in (".config/autostart", ".local/share/applications"):
        old = os.path.join(home, folder, f"talktype{suffix}.desktop")
        new = os.path.join(home, folder, f"tuxtalk{suffix}.desktop")
        if not os.path.isfile(old):
            continue
        try:
            if not os.path.exists(new):
                with open(old) as f:
                    text = _rewrite_entry(f.read(), dev)
                tmp = new + ".tmp"
                with open(tmp, "w") as f:
                    f.write(text)
                os.replace(tmp, new)
                done.append(f"moved {folder}/talktype{suffix}.desktop to tuxtalk{suffix}.desktop")
            else:
                done.append(f"removed {folder}/talktype{suffix}.desktop (tuxtalk{suffix}.desktop exists)")
            os.remove(old)
        except OSError as e:
            done.append(f"could not move {folder}/talktype{suffix}.desktop: {e}")
    return done

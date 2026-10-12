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

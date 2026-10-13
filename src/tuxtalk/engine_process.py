"""
Keeping TuxTalk's helper engines on a short leash.

TuxTalk runs its optional background engines as separate programs: the AI
cleanup engine (llama-server, ai_cleanup.py) and the Vulkan graphics engine
(whisper_vulkan.py, and parakeet_gpu.py for Parakeet). Each can hold a gigabyte
or more of memory, so none may outlive the dictation service that started it.
"""
import os
import signal

from .logger import setup_logger

logger = setup_logger(__name__)


def set_parent_death_signal():
    """Runs in the child before exec: if the dictation service dies, even by
    SIGKILL, the kernel kills the engine too, so it cannot sit orphaned on a
    gigabyte of memory.

    SIGKILL, not SIGTERM: llama-server sometimes stalls in its graceful
    shutdown and then ignores SIGTERM, and no engine holds state worth saving.

    The signal fires when the thread that called Popen exits, not the
    process, so spawn from a thread that lives as long as the engine (see
    parakeet_gpu's _launcher)."""
    try:
        import ctypes
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG
    except Exception:
        pass


def remove_other_versions(parent, keep):
    """Delete every engine version folder under *parent* except *keep*. Each
    version unpacks into its own folder, so without this an update leaves
    the old one behind for good. Never raises."""
    import shutil
    try:
        names = os.listdir(parent)
    except OSError:
        return
    for name in names:
        path = os.path.join(parent, name)
        if name != keep and os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=True)
            logger.info(f"Removed an older engine version: {path}")


def processes_of(binary):
    """(pid, parent pid) of every running process started from *binary*."""
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as f:
                argv0 = f.read().split(b"\0", 1)[0].decode(errors="replace")
            if argv0 != binary:
                continue
            with open(f"/proc/{entry}/stat") as f:
                ppid = int(f.read().rsplit(")", 1)[1].split()[1])
            found.append((int(entry), ppid))
        except (OSError, ValueError, IndexError):
            continue
    return found


def is_talktype_process(pid) -> bool:
    """True when *pid* is our app, under its current name (TuxTalk) or the
    old one (TalkType: an older copy, or the dev folder ~/Projects/TalkType)."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmdline = f.read().lower()
        return b"tuxtalk" in cmdline or b"talktype" in cmdline
    except OSError:
        return False


def kill_orphans(processes, is_talktype, label) -> int:
    """Kill the engines in *processes* whose parent is no longer TuxTalk.
    A self-healing backstop for the parent-death signal. Returns how many."""
    killed = 0
    for pid, ppid in processes:
        if ppid == os.getpid() or is_talktype(ppid):
            continue
        try:
            os.kill(pid, signal.SIGKILL)
            killed += 1
            logger.warning(f"Killed an orphaned {label} left by an earlier run (pid {pid})")
        except OSError:
            pass
    return killed

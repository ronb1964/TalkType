"""
Keeping TalkType's helper engines on a short leash.

TalkType runs two optional background engines as separate programs: the AI
cleanup engine (llama-server, ai_cleanup.py) and the AMD / Intel graphics
engine (whisper-server, whisper_vulkan.py). Each can hold a gigabyte or more
of memory, so neither may outlive the dictation service that started it.
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
    shutdown and then ignores SIGTERM. That left orphaned engines running for
    hours on a real machine (2026-09-26). Neither engine holds state worth saving."""
    try:
        import ctypes
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG
    except Exception:
        pass


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
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return b"talktype" in f.read().lower()
    except OSError:
        return False


def kill_orphans(processes, is_talktype, label) -> int:
    """Kill the engines in *processes* whose parent is no longer TalkType.
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

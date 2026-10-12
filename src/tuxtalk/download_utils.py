"""
Shared download helpers: timeouts, cancellation, integrity verification.

Replaces three divergent download implementations that each had a gap:
- cuda_helper used urlretrieve (supports no timeout — a stalled connection
  hung forever and the Cancel button stopped working)
- extension_helper used urlretrieve the same way
- update_checker had its own loop but no truncation check and no checksum

Every download goes to a ".tmp" file first and is atomically renamed into
place only after size and (when provided) sha256 checks pass — so an
interrupted download can never be mistaken for a complete file.
"""

import hashlib
import logging
import os
import shutil
import urllib.request

logger = logging.getLogger(__name__)

# Read in 64 KiB chunks — large enough for throughput, small enough that
# cancellation and progress updates stay responsive.
_CHUNK_SIZE = 65536


def download_file(
    url: str,
    dest_path: str,
    timeout: int = 60,
    cancel_event=None,
    progress_hook=None,
    expected_sha256: str | None = None,
    user_agent: str = "TalkType",
) -> bool:
    """Download *url* to *dest_path* safely. Returns True on success.

    - *timeout* applies to each socket operation, so a stalled connection
      raises instead of hanging forever.
    - *cancel_event* (threading.Event) is checked between chunks; setting it
      aborts within one chunk read.
    - *progress_hook(downloaded_bytes, total_bytes)* is called per chunk
      (total_bytes is 0 when the server sends no Content-Length).
    - *expected_sha256* is verified before the file lands at dest_path.
    - Truncated transfers are rejected: HTTP read() returns b"" on a
      premature EOF without raising, so the byte count is compared against
      Content-Length explicitly.

    On any failure the partial ".tmp" file is removed and dest_path is left
    untouched.
    """
    tmp_path = dest_path + ".tmp"
    sha = hashlib.sha256()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            total = int(response.headers.get("Content-Length", 0) or 0)
            downloaded = 0
            parent = os.path.dirname(tmp_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(tmp_path, "wb") as f:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise InterruptedError("Download cancelled")
                    chunk = response.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    sha.update(chunk)
                    downloaded += len(chunk)
                    if progress_hook:
                        progress_hook(downloaded, total)

        if total and downloaded != total:
            logger.error(
                f"Download truncated: got {downloaded} of {total} bytes from {url}"
            )
            _remove_quiet(tmp_path)
            return False

        if expected_sha256:
            actual = sha.hexdigest()
            if actual.lower() != expected_sha256.strip().lower():
                logger.error(
                    f"Checksum mismatch for {url}: expected {expected_sha256}, got {actual}"
                )
                _remove_quiet(tmp_path)
                return False

        os.replace(tmp_path, dest_path)
        return True

    except InterruptedError:
        logger.info(f"Download cancelled: {url}")
        _remove_quiet(tmp_path)
        return False
    except Exception as e:
        logger.error(f"Download failed for {url}: {e}")
        _remove_quiet(tmp_path)
        return False


def _remove_quiet(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def sha256_of_file(path: str) -> str:
    """Hex sha256 digest of a file, streamed (no full read into memory)."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK_SIZE)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


def parse_sha256sums(text: str) -> dict:
    """Parse `sha256sum` output ("<hash>  <filename>") into {filename: hash}.

    Handles the optional '*' binary-mode marker before the filename and
    skips blank/comment lines.
    """
    sums = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest, filename = parts
        sums[filename.lstrip("*").strip()] = digest
    return sums


def free_space_bytes(path: str) -> int:
    """Free disk space (bytes) on the filesystem holding *path*.

    Walks up to the nearest existing parent so it works for directories
    that haven't been created yet. Returns 0 if nothing can be determined
    (callers should treat 0 as 'unknown', not 'full').
    """
    p = os.path.abspath(path)
    while p and not os.path.exists(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    try:
        return shutil.disk_usage(p).free
    except Exception:
        return 0

"""The repository must be able to build and release itself from a clean clone.

build-release.sh is tracked in git, but the scripts it calls were once listed in
.gitignore under "Dev/test scripts". They are not dev scripts — they are the
release toolchain, and with them missing a fresh clone dies immediately with
"No such file or directory". The whole ability to ship existed only as untracked
files on one machine.
"""

import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Everything the documented release process in CLAUDE.md needs in order to run.
REQUIRED_IN_GIT = [
    "build-release.sh",        # step 3
    "container-build.sh",      # called by build-release.sh
    "patch_pytorch.py",        # called by container-build.sh
    "package-extension.sh",    # step 10
    "fresh-start-for-testing.sh",  # step 6
]


def tracked_files():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    return set(out.stdout.split())


@pytest.mark.parametrize("path", REQUIRED_IN_GIT)
def test_release_toolchain_is_tracked(path):
    assert path in tracked_files(), (
        f"{path} is needed to build or release TalkType but is not in git. "
        f"A fresh clone cannot ship a release without it."
    )


def test_build_script_calls_nothing_that_is_missing_from_git():
    """Catches a new dependency being added and left untracked."""
    tracked = tracked_files()
    missing = []

    for script in ("build-release.sh", "container-build.sh"):
        script_path = ROOT / script
        if not script_path.exists():
            continue
        text = script_path.read_text()
        # Files referenced as /build/<name> inside the container, and as
        # ./<name> or bare <name>.sh / <name>.py from the project root.
        for name in re.findall(r"/build/([A-Za-z0-9_.-]+\.(?:sh|py))", text):
            if (ROOT / name).exists() and name not in tracked:
                missing.append(f"{script} -> {name}")

    assert not missing, (
        "the build calls files that exist locally but are not in git:\n  "
        + "\n  ".join(missing)
    )


# --- patch_pytorch must not claim success when it patched nothing -----------

def test_patch_pytorch_fails_loudly_when_the_target_line_is_gone(tmp_path):
    """The script looks for the exact line "_load_global_deps()" and wraps it
    in a try/except so PyTorch tolerates missing CUDA libraries.

    If a PyTorch upgrade changes that line, the loop simply finds nothing, the
    file is rewritten byte-identical, and the script still prints its success
    tick and exits 0. container-build.sh carries on and ships an AppImage
    whose PyTorch crashes on any machine without CUDA — with nothing in the
    build log to suggest the patch had silently become a no-op.
    """
    target = tmp_path / "__init__.py"
    original = "import os\n\n# nothing to patch here\n_load_global_deps_renamed()\n"
    target.write_text(original)

    result = subprocess.run(
        ["python3", str(ROOT / "patch_pytorch.py"), str(target)],
        capture_output=True, text=True,
    )

    assert result.returncode != 0, (
        f"reported success without patching anything: {result.stdout!r}"
    )
    assert target.read_text() == original, "rewrote the file despite patching nothing"


def test_patch_pytorch_succeeds_on_a_normal_pytorch_init(tmp_path):
    target = tmp_path / "__init__.py"
    target.write_text("import os\n\nif True:\n    _load_global_deps()\n")

    result = subprocess.run(
        ["python3", str(ROOT / "patch_pytorch.py"), str(target)],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    patched = target.read_text()
    assert "try:" in patched
    assert "except Exception:" in patched
    assert "_load_global_deps()" in patched


def test_patch_pytorch_is_idempotent(tmp_path):
    """container-build.sh may run it more than once; a second run must not
    double-wrap or start failing."""
    target = tmp_path / "__init__.py"
    target.write_text("import os\n\nif True:\n    _load_global_deps()\n")

    first = subprocess.run(["python3", str(ROOT / "patch_pytorch.py"), str(target)],
                           capture_output=True, text=True)
    assert first.returncode == 0
    after_first = target.read_text()

    second = subprocess.run(["python3", str(ROOT / "patch_pytorch.py"), str(target)],
                            capture_output=True, text=True)

    assert second.returncode == 0, (
        f"a second run failed, which would break a rebuild: {second.stderr!r}"
    )
    assert target.read_text() == after_first, "double-patched on the second run"

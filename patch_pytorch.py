#!/usr/bin/env python3
"""Patch PyTorch to gracefully handle missing CUDA libraries.

Wraps torch/__init__.py's `_load_global_deps()` call in a try/except so an
AppImage built with CPU-only PyTorch still starts on machines with no CUDA
libraries present.

Exits non-zero if it could not find anything to patch. That matters: this runs
inside container-build.sh, and the previous version simply fell out of its
search loop, rewrote the file unchanged, printed a success tick and exited 0.
A PyTorch upgrade that renamed or moved the call would therefore produce an
AppImage that crashes on every machine without CUDA, with nothing in the build
log to show the patch had quietly become a no-op.
"""
import sys

# Written into the patched source so a re-run can recognise its own work
# instead of wrapping the call a second time.
MARKER = "# TalkType: tolerate missing CUDA libraries"

if len(sys.argv) != 2:
    print("Usage: patch_pytorch.py <path_to_torch/__init__.py>", file=sys.stderr)
    sys.exit(1)

torch_init = sys.argv[1]

try:
    with open(torch_init, 'r') as f:
        lines = f.readlines()
except OSError as e:
    print(f"✗ Could not read {torch_init}: {e}", file=sys.stderr)
    sys.exit(1)

if any(MARKER in line for line in lines):
    print("✓ PyTorch already patched — leaving it alone")
    sys.exit(0)

# Find and wrap the _load_global_deps() call
patched = False
for i, line in enumerate(lines):
    if line.strip() == '_load_global_deps()':
        indent = line[:len(line) - len(line.lstrip())]
        lines[i] = (
            f'{indent}try:  {MARKER}\n'
            f'{indent}    _load_global_deps()\n'
            f'{indent}except Exception:\n'
            f'{indent}    pass  # Ignore CUDA errors\n'
        )
        patched = True
        break

if not patched:
    print(
        f"✗ Could not find '_load_global_deps()' in {torch_init}.\n"
        f"  PyTorch's startup code has changed shape, so this patch no longer\n"
        f"  applies. Building on would ship an AppImage that crashes on any\n"
        f"  machine without CUDA libraries. Fix the patch before releasing.",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    with open(torch_init, 'w') as f:
        f.writelines(lines)
except OSError as e:
    print(f"✗ Could not write {torch_init}: {e}", file=sys.stderr)
    sys.exit(1)

print("✓ PyTorch patched for CPU/GPU flexibility")

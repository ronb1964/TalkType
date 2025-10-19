#!/usr/bin/env python3
"""Patch PyTorch to gracefully handle missing CUDA libraries."""
import sys

if len(sys.argv) != 2:
    print("Usage: patch_pytorch.py <path_to_torch/__init__.py>")
    sys.exit(1)

torch_init = sys.argv[1]

with open(torch_init, 'r') as f:
    lines = f.readlines()

# Find and wrap the _load_global_deps() call
for i, line in enumerate(lines):
    if line.strip() == '_load_global_deps()':
        indent = line[:len(line) - len(line.lstrip())]
        lines[i] = f'{indent}try:\n{indent}    _load_global_deps()\n{indent}except Exception:\n{indent}    pass  # Ignore CUDA errors\n'
        break

with open(torch_init, 'w') as f:
    f.writelines(lines)

print("✓ PyTorch patched for CPU/GPU flexibility")

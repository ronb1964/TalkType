#!/usr/bin/env python3
"""
PyTorch CUDA Library Initialization for TalkType AppImage

This module MUST be imported before any PyTorch imports.
It solves PyTorch's limitation of only searching sys.path (not LD_LIBRARY_PATH).
"""

import sys
import os
import ctypes
import warnings
from pathlib import Path

# CRITICAL: Check for CUDA libraries BEFORE any imports that might load PyTorch
# If CUDA libs don't exist, disable CUDA to prevent PyTorch from trying to load them
cuda_base = Path.home() / ".local" / "share" / "TalkType" / "cuda"
lib_path = cuda_base / "lib"

if not lib_path.exists():
    # No CUDA libraries - force CPU-only mode before PyTorch can initialize
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    print("✓ No CUDA libraries found - forcing CPU-only mode")

    # Suppress PyTorch CUDA library warnings since we're in CPU-only mode
    warnings.filterwarnings('ignore', message='Could not load CUDA library.*')
    warnings.filterwarnings('ignore', message='.*not found in the system path.*')

# Track if initialization has already run (prevent duplicate messages)
_initialized = False


def init_cuda_for_pytorch():
    """
    Initialize CUDA library paths for PyTorch in AppImage environment.

    PyTorch searches for CUDA libraries in sys.path using patterns like:
    {sys.path}/nvidia/{lib_folder}/lib/{lib_name}

    However, our cuda_helper.py strips the 'nvidia/' prefix when extracting,
    so libraries are at: ~/.local/share/TalkType[-dev]/cuda/lib/{lib_folder}/lib/
    We need to create the 'nvidia' directory structure PyTorch expects.

    Returns:
        bool: True if CUDA libraries were found and initialized, False otherwise
    """
    global _initialized
    if _initialized:
        return True  # Already initialized, skip duplicate work

    from .cuda_helper import get_appdir_cuda_path
    cuda_base = Path(get_appdir_cuda_path())
    lib_path = cuda_base / "lib"

    if not lib_path.exists():
        # Already handled at module import time
        _initialized = True
        return False

    # Create nvidia symlink if it doesn't exist
    # PyTorch expects: {sys.path}/nvidia/{lib_folder}/lib/
    # We have: cuda/lib/{lib_folder}/lib/
    # Solution: Create cuda/nvidia -> cuda/lib symlink
    nvidia_link = cuda_base / "nvidia"
    if not nvidia_link.exists():
        try:
            nvidia_link.symlink_to(lib_path)
            print(f"✓ Created nvidia symlink for PyTorch")
        except Exception as e:
            print(f"⚠ Failed to create nvidia symlink: {e}")

    # Add CUDA directory to sys.path so PyTorch can find nvidia/* subdirectories
    cuda_str = str(cuda_base)
    if cuda_str not in sys.path:
        sys.path.insert(0, cuda_str)
        print(f"✓ Added {cuda_str} to sys.path for PyTorch")

    # Preload critical CUDA libraries with ctypes (belt-and-suspenders approach)
    # This ensures libraries are loaded even if PyTorch's search logic changes
    # Our structure: cuda/lib/{lib_folder}/lib/{lib_name}
    # Use glob patterns to support any CUDA version (not hardcoded to .so.12 or .so.9)
    import glob

    lib_patterns = [
        ("cuda_runtime", "lib", "libcudart.so.*"),
        ("cublas", "lib", "libcublas.so.*"),
        ("cublas", "lib", "libcublasLt.so.*"),
        ("cudnn", "lib", "libcudnn.so.*"),
    ]

    loaded_count = 0
    for lib_folder, lib_subdir, lib_pattern in lib_patterns:
        search_path = lib_path / lib_folder / lib_subdir / lib_pattern
        matches = glob.glob(str(search_path))

        if matches:
            # Load the first match (usually there's only one version)
            lib_file = matches[0]
            try:
                # Load with RTLD_GLOBAL to make symbols globally available
                ctypes.CDLL(lib_file, mode=ctypes.RTLD_GLOBAL)
                loaded_count += 1
            except Exception as e:
                lib_name = Path(lib_file).name
                print(f"⚠ Failed to preload {lib_name}: {e}")

    if loaded_count > 0:
        print(f"✓ Preloaded {loaded_count} CUDA libraries for PyTorch")
        _initialized = True
        return True

    _initialized = True
    return False


# Auto-initialize when module is imported
if __name__ != "__main__":
    init_cuda_for_pytorch()

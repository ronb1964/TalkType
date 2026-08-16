#!/usr/bin/env python3
"""Step A of the Flatpak GPU spike: can the sandbox see + initialize the NVIDIA GPU?

Pure ctypes against libcuda.so.1 (the NVIDIA *driver* API) — no numpy, torch, or
ctranslate2. libcuda is supplied by the host driver via Flatpak's NVIDIA GL
extension; the CUDA *toolkit* libs (cudart/cublas/cudnn) are a separate, already-
solved library-loading concern. So if cuInit + cuDeviceGetCount + cuDeviceGetName
print the card from inside a Flatpak, the one thing a sandbox can actually block —
driver + device-node access — works, and the rest is just LD_LIBRARY_PATH.

Mirrors the libei ctypes discipline from the portal spike: set restype/argtypes on
EVERY call, or 64-bit pointers silently truncate to 32-bit -> SIGSEGV.
"""
import ctypes
import ctypes.util
import os
import sys

# libcuda lands here inside a Flatpak when the NVIDIA GL extension is mounted.
_CANDIDATES = (
    "libcuda.so.1",
    "libcuda.so",
    "/usr/lib/x86_64-linux-gnu/GL/nvidia/lib/libcuda.so.1",
    "/usr/lib/x86_64-linux-gnu/GL/default/lib/libcuda.so.1",
    "/usr/lib/x86_64-linux-gnu/libcuda.so.1",
    "/usr/lib/GL/nvidia/lib/libcuda.so.1",
)


def _load_libcuda():
    tried = []
    found = ctypes.util.find_library("cuda")
    for name in ([found] if found else []) + list(_CANDIDATES):
        try:
            return ctypes.CDLL(name), name
        except OSError as e:
            tried.append(f"{name}: {e}")
    print("could not load libcuda; tried:")
    for t in tried:
        print(f"  - {t}")
    return None, None


def main():
    print(f"FLATPAK_ID={os.environ.get('FLATPAK_ID', '(none)')}")
    print(f"LD_LIBRARY_PATH={os.environ.get('LD_LIBRARY_PATH', '(unset)')}")
    print("device nodes:")
    for node in ("/dev/nvidia0", "/dev/nvidiactl", "/dev/nvidia-uvm", "/dev/dri"):
        print(f"  {node}: {'present' if os.path.exists(node) else 'MISSING'}")

    lib, path = _load_libcuda()
    if lib is None:
        print("RESULT: FAIL — libcuda not loadable in sandbox")
        return 2
    print(f"loaded libcuda from: {path}")

    lib.cuInit.restype = ctypes.c_int
    lib.cuInit.argtypes = [ctypes.c_uint]
    rc = lib.cuInit(0)
    if rc != 0:
        print(f"RESULT: FAIL — cuInit returned {rc} (403=CUDA_ERROR_NOT_INITIALIZED, "
              f"999=UNKNOWN/no device access)")
        return 3

    lib.cuDeviceGetCount.restype = ctypes.c_int
    lib.cuDeviceGetCount.argtypes = [ctypes.POINTER(ctypes.c_int)]
    count = ctypes.c_int(0)
    rc = lib.cuDeviceGetCount(ctypes.byref(count))
    if rc != 0:
        print(f"RESULT: FAIL — cuDeviceGetCount returned {rc}")
        return 4
    print(f"cuDeviceGetCount = {count.value}")
    if count.value < 1:
        print("RESULT: FAIL — no CUDA devices visible in sandbox")
        return 5

    lib.cuDeviceGet.restype = ctypes.c_int
    lib.cuDeviceGet.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_int]
    dev = ctypes.c_int(0)
    lib.cuDeviceGet(ctypes.byref(dev), 0)

    lib.cuDeviceGetName.restype = ctypes.c_int
    lib.cuDeviceGetName.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    buf = ctypes.create_string_buffer(256)
    lib.cuDeviceGetName(buf, 256, dev)
    print(f"cuDeviceGetName = {buf.value.decode(errors='replace')}")
    print("RESULT: PASS — sandbox has NVIDIA driver + device access")
    return 0


if __name__ == "__main__":
    sys.exit(main())

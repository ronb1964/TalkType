Hi @probonopd,

Thank you for identifying the glibc compatibility issue! You're absolutely right - the AppImage I submitted was accidentally built with binaries from my Fedora development system (which has GLIBC 2.38) instead of Ubuntu 22.04.

## Root Cause

The build script was copying Python binaries from a virtual environment that symlinked to the host system's Python, rather than using Ubuntu 22.04's native Python 3.10.

## Fix Applied

I've updated the build process to:

1. **Always use system Python directly** - Priority given to Ubuntu paths (`/usr/bin/python3.10`, `/usr/lib/x86_64-linux-gnu/`) before Fedora paths
2. **Use `--copies` flag for venv** - This prevents symlink issues that caused host contamination
3. **Add glibc verification** - The build script now checks and reports glibc requirements during the build

## Rebuilding Now

I'm rebuilding the AppImage inside a clean Ubuntu 22.04 container to ensure it targets GLIBC 2.35. I'll update the GitHub release and this PR once the new build is tested and verified.

**Question:** To answer your question about the oldest Ubuntu version - the new build should work on **Ubuntu 22.04 LTS (Jammy)** and newer, which has GLIBC 2.35.

I apologize for the confusion and appreciate your patience!

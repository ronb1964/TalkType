# TalkType Project Rules for Claude

## CRITICAL: DO NOT BUILD WITHOUT PERMISSION

**NEVER run `./build-release.sh` or build an AppImage without explicitly asking Ron first.**

Before building, always ask: "Ready to build the AppImage?" and wait for confirmation.

There may be other fixes needed before building. Don't assume the work is done.

## After Building

Always copy the AppImage to `~/AppImages/` folder after building:
```bash
cp TalkType-v*.AppImage ~/AppImages/
chmod +x ~/AppImages/TalkType-v*.AppImage
```

## Testing

Ron tests from `~/AppImages/` - never ask him to run from the project folder.

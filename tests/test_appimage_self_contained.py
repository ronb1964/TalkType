"""The AppImage must start on systems that lack libfuse2 or the tray library.

AppImageHub's test (AppImage/appimage.github.io#3511, 2026-09-26) failed the
0.10.0 AppImage twice over:

- The tray crashed with "Could not locate app_indicator_new:
  libayatana-appindicator3.so.1". Only the typelib was bundled, and a typelib
  merely describes a library; the real .so still came from the system.
- It was built by the retired AppImageKit appimagetool, whose runtime needs
  libfuse2. Ubuntu 26.04 does not ship libfuse2, so the AppImage did not start.

These are build-script checks: the real proof is the AppImage, but a revert
of either line would otherwise go unnoticed until users hit it.
"""

import pathlib

BUILD = (pathlib.Path(__file__).resolve().parent.parent / "container-build.sh").read_text()


def test_uses_current_appimagetool_not_appimagekit():
    assert "AppImage/appimagetool/releases" in BUILD
    assert "AppImageKit/releases" not in BUILD, (
        "container-build.sh downloads the retired AppImageKit appimagetool, "
        "whose runtime needs libfuse2 on the user's system"
    )


def test_tray_library_itself_is_bundled():
    assert "libayatana-appindicator3.so.1" in BUILD
    assert "cp -L \"$APPINDICATOR_LIB\" AppDir/usr/lib/" in BUILD, (
        "the tray library .so must be copied into the AppImage, not just its typelib"
    )

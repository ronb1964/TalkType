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


def test_portaudio_fallback_is_bundled_off_the_library_path():
    # talktype/__init__.py expects it at usr/lib/portaudio/, and it must not
    # sit in usr/lib, which is on LD_LIBRARY_PATH (see container-build.sh).
    assert "PA_DIR=AppDir/usr/lib/portaudio" in BUILD
    assert "libportaudio.so.2 libjack.so.0 libdb-5.3.so" in BUILD


def test_update_information_is_embedded_and_its_zsync_is_released():
    """AppImageHub warned: no update information (AppImage/appimage.github.io#4598)."""
    assert '-u "$UPDATE_INFO"' in BUILD
    assert "gh-releases-zsync|ronb1964|TalkType|latest|TalkType-*x86_64.AppImage.zsync" in BUILD
    claude_md = (pathlib.Path(__file__).resolve().parent.parent / "CLAUDE.md").read_text()
    assert "TalkType-vX.X.X-x86_64.AppImage.zsync" in claude_md, (
        "the release checklist must upload the .zsync the update information points at")

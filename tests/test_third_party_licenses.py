"""Bundled third-party software must ship with its license (0.14.7).

The AppImage (and so the .deb and .rpm, which repackage it) carries ydotool
(AGPL-3.0-or-later), wl-clipboard (GPL-3.0-or-later), Python packages and
libraries copied from Ubuntu. packaging/collect-licenses.sh puts all their
licenses into the AppImage and fails the build if one is missing; these tests
keep the wiring, and the versions named in THIRD_PARTY_LICENSES.md, honest.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = (ROOT / "container-build.sh").read_text()
COLLECT = (ROOT / "packaging/collect-licenses.sh").read_text()
NOTICE = (ROOT / "THIRD_PARTY_LICENSES.md").read_text()


def _var(name):
    m = re.search(rf"^{name}=(\S+)$", BUILD, re.M)
    assert m, f"container-build.sh no longer sets {name}"
    return m.group(1)


def test_ydotool_is_pinned_and_the_notice_names_that_commit():
    # It used to build whatever ydotool's latest code was, so no notice could
    # say which version shipped.
    commit = _var("YDOTOOL_COMMIT")
    assert re.fullmatch(r"[0-9a-f]{40}", commit)
    assert 'git checkout -q "$YDOTOOL_COMMIT"' in BUILD
    assert f"`{commit}`" in NOTICE


def test_the_notice_names_the_wl_clipboard_version_that_is_built():
    assert f"`{_var('WL_CLIPBOARD_VERSION')}`" in NOTICE


def test_the_notice_states_each_copyleft_license_and_its_source():
    assert "AGPL-3.0-or-later" in NOTICE and "https://github.com/ReimuNotMoe/ydotool" in NOTICE
    assert "GPL-3.0-or-later" in NOTICE and "https://github.com/bugaevc/wl-clipboard" in NOTICE


def test_licenses_are_collected_after_the_last_copy_into_the_appimage():
    call = BUILD.index("bash packaging/collect-licenses.sh AppDir /tmp/ydotool /tmp/wl-clipboard")
    last_copy = max(m.start() for m in re.finditer(r"^cp .*AppDir", BUILD, re.M))
    assert last_copy < call < BUILD.index("appimagetool")


def test_the_collector_ships_every_license_and_fails_when_one_is_missing():
    for needle in ('"$YDOTOOL_SRC/LICENSE"', '"$WLCLIP_SRC/COPYING"',
                   '"$PROJECT/LICENSE" "$PROJECT/THIRD_PARTY_LICENSES.md"',
                   "licenses/ctranslate2-LICENSE", "licenses/tokenizers-LICENSE",
                   "/usr/share/doc/$pkg/copyright"):
        assert needle in COLLECT, needle
    assert "set -euo pipefail" in COLLECT
    assert COLLECT.count("exit 1") >= 2   # no package found / no copyright file


def test_the_licenses_wheels_leave_out_are_kept_in_the_repo():
    # CTranslate2's and tokenizers' wheels ship no license file of their own.
    assert (ROOT / "packaging/licenses/ctranslate2-LICENSE").read_text().startswith("MIT License")
    assert "Apache License" in (ROOT / "packaging/licenses/tokenizers-LICENSE").read_text()


def test_deb_and_rpm_refuse_an_appimage_without_licenses():
    for script, place in (("build-deb.sh", "usr/share/doc/talktype"),
                          ("build-rpm.sh", "usr/share/licenses/talktype")):
        text = (ROOT / script).read_text()
        assert "ydotool/LICENSE wl-clipboard/COPYING" in text, script
        assert "rebuild it with ./build-release.sh" in text, script
        assert place in text, script

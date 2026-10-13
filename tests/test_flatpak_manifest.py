"""The Flatpak manifests agree with the app they package.

Nothing builds the Flatpak in CI, so a rename can leave a manifest copying a
folder that no longer exists or exporting files under a different app ID
(Flatpak only exports desktop files, icons and metainfo named after its
app-id). These checks read the manifests as text and catch both.
"""
import pathlib
import re

import pytest

from tuxtalk import config

ROOT = pathlib.Path(__file__).resolve().parent.parent
FLATPAK = ROOT / "packaging" / "flatpak"
MANIFESTS = [FLATPAK / f"{config.APP_ID}.yml",
             FLATPAK / "flathub" / f"{config.APP_ID}.yml"]


@pytest.mark.parametrize("manifest", MANIFESTS, ids=["local", "flathub"])
def test_app_id_matches_the_code(manifest):
    text = manifest.read_text()
    assert re.search(r"^app-id: (\S+)$", text, re.M).group(1) == config.APP_ID


@pytest.mark.parametrize("manifest", MANIFESTS, ids=["local", "flathub"])
def test_exported_files_are_named_after_the_app_id(manifest):
    text = manifest.read_text()
    exported = re.findall(r"/app/share/(?:applications|metainfo|icons/\S+/apps)/(\S+)", text)
    assert exported, "no desktop file, metainfo or icon installed"
    for name in exported:
        assert name.startswith(config.APP_ID + "."), name


@pytest.mark.parametrize("manifest", MANIFESTS, ids=["local", "flathub"])
def test_package_lands_where_the_launcher_imports_it(manifest):
    text = manifest.read_text()
    launcher = (FLATPAK / "talktype-launcher").read_text()
    package = re.search(r"python3 -m (\w+)\.tray", launcher).group(1)
    assert "PYTHONPATH=\"/app/lib:" in launcher
    copy = re.search(r"cp -r (\S+) /app/lib/(\S+)", text)
    assert copy.group(2) == package
    assert pathlib.PurePosixPath(copy.group(1)).name == package


def test_local_manifest_copies_a_folder_that_exists():
    text = MANIFESTS[0].read_text()
    source = re.search(r"- type: dir\s+path: (\S+)", text).group(1)
    copied = re.search(r"cp -r (\S+) /app/lib/", text).group(1)
    assert (FLATPAK / source / copied).is_dir()


def test_build_script_uses_the_renamed_manifest():
    script = (FLATPAK / "build-flatpak.sh").read_text()
    assert f'MANIFEST="$HERE/{config.APP_ID}.yml"' in script
    assert f"APPID={config.APP_ID}" in script

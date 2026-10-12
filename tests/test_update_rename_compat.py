"""0.14.x installs must update across the rename (TalkType -> TuxTalk, 0.15.0).

These run against the updater as it stands BEFORE the rename. Passing proves
every installed TalkType finds, and checksum-verifies, a TuxTalk release.
"""
import io
import json

from talktype import update_checker as uc

RELEASE = {
    "tag_name": "v0.15.0", "name": "TuxTalk 0.15.0", "body": "", "published_at": "",
    "html_url": "https://github.com/ronb1964/TuxTalk/releases/tag/v0.15.0",
    "assets": [
        {"name": "TuxTalk-v0.15.0-x86_64.AppImage", "browser_download_url": "A"},
        {"name": "TuxTalk-v0.15.0-x86_64.AppImage.zsync", "browser_download_url": "Z"},
        {"name": "TalkType-v0.15.0-x86_64.AppImage.zsync", "browser_download_url": "Z2"},
        {"name": "tuxtalk_0.15.0_amd64.deb", "browser_download_url": "D"},
        {"name": "tuxtalk-0.15.0-1.x86_64.rpm", "browser_download_url": "R"},
        {"name": "tuxtalk-gnome-extension.zip", "browser_download_url": "E"},
        {"name": "SHA256SUMS.txt", "browser_download_url": "S"},
    ],
}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_old_client_picks_every_tuxtalk_asset(monkeypatch):
    monkeypatch.setattr(uc.urllib.request, "urlopen",
                        lambda *a, **k: _Resp(json.dumps(RELEASE).encode()))
    r = uc.fetch_latest_release()
    assert r["appimage_url"] == "A" and r["appimage_name"] == "TuxTalk-v0.15.0-x86_64.AppImage"
    assert (r["deb_url"], r["rpm_url"], r["extension_url"], r["checksums_url"]) == ("D", "R", "E", "S")


def test_old_client_finds_the_tuxtalk_checksum(monkeypatch):
    sums = "ab" * 32 + "  TuxTalk-v0.15.0-x86_64.AppImage\n" + "cd" * 32 + "  tuxtalk_0.15.0_amd64.deb\n"
    monkeypatch.setattr(uc.urllib.request, "urlopen", lambda *a, **k: _Resp(sums.encode()))
    assert uc.fetch_expected_sha256("https://example.invalid/SHA256SUMS.txt", "TuxTalk-v0.15.0-x86_64.AppImage") == "ab" * 32

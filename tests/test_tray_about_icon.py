"""The About dialog finds TuxTalk's icon.

No install has hicolor/128x128/apps/talktype.png or a src/tuxtalk/icons
folder, so looking only there would leave About without an icon.
"""
from tuxtalk import tray


def test_a_real_icon_file_is_used(monkeypatch, tmp_path):
    svg = tmp_path / "icon.svg"
    svg.write_text("<svg/>")
    monkeypatch.setattr("tuxtalk.autostart.get_icon_path", lambda: str(svg))
    assert tray.about_icon_source(lambda name: False) == ("file", str(svg))


def test_the_appimage_bundled_svg_is_used(monkeypatch, tmp_path):
    (tmp_path / "io.github.ronb1964.TuxTalk.svg").write_text("<svg/>")
    monkeypatch.setattr("tuxtalk.autostart.get_icon_path", lambda: "audio-input-microphone")
    monkeypatch.setenv("APPDIR", str(tmp_path))
    assert tray.about_icon_source(lambda name: False) == (
        "file", str(tmp_path / "io.github.ronb1964.TuxTalk.svg"))


def test_the_icon_theme_is_the_fallback(monkeypatch):
    monkeypatch.setattr("tuxtalk.autostart.get_icon_path", lambda: "audio-input-microphone")
    monkeypatch.delenv("APPDIR", raising=False)
    assert tray.about_icon_source(lambda name: name == "tuxtalk") == ("icon", "tuxtalk")
    assert tray.about_icon_source(lambda name: True) == ("icon", "io.github.ronb1964.TuxTalk")
    assert tray.about_icon_source(lambda name: False) is None

"""Color/backing helpers and the waveform/bars/radial renderers.

Pure cairo — every renderer is exercised by drawing onto a headless
ImageSurface, so these run without a display. Geometry and colors were settled
by live prototyping; see the design spec dated 2026-08-14.
"""
import numpy as np
import pytest

from talktype import indicator_styles as S


def test_backing_alpha_endpoints_and_monotonic():
    assert S.backing_alpha(0.0, 0.5) == pytest.approx(0.5)
    assert S.backing_alpha(1.0, 0.5) == pytest.approx(0.0, abs=1e-9)
    xs = [i / 50 for i in range(51)]
    vals = [S.backing_alpha(r, 0.5) for r in xs]
    assert all(vals[i] >= vals[i + 1] - 1e-9 for i in range(len(vals) - 1))


def test_backing_off_is_zero():
    assert S.backing_alpha(0.0, 0.0) == 0.0
    assert S.BACKING_LEVELS["off"] == 0.0
    assert set(S.BACKING_LEVELS) == {"off", "soft", "medium", "strong"}


def test_resolve_color_system_uses_accent():
    assert S.resolve_color("system", "#48b7f5", (0.2, 0.4, 0.26)) == (0.2, 0.4, 0.26)


def test_resolve_color_custom_parses_hex():
    r, g, b = S.resolve_color("custom", "#ff8000", (0, 0, 0))
    assert r == pytest.approx(1.0, abs=0.01)
    assert g == pytest.approx(0.5, abs=0.02)
    assert b == pytest.approx(0.0, abs=0.01)


def test_resolve_color_classic_is_cyan():
    assert S.resolve_color("classic", "#ff8000", (0.2, 0.4, 0.26)) == S.CLASSIC_CYAN


def test_orb_palette_derives_from_the_base_color():
    """The orb recolor keeps its structure, only the hue changing."""
    pal = S.orb_palette((0.9, 0.2, 0.2))   # red
    assert pal["glow"] == (0.9, 0.2, 0.2)
    assert pal["p_far"] == (0.9, 0.2, 0.2)
    # core runs white-hot center to a dark edge
    assert pal["core"][0][1] == (1.0, 1.0, 1.0)
    assert len(pal["core"]) == 5


def _has_ink(draw):
    cairo = pytest.importorskip("cairo")
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 120)
    cr = cairo.Context(surf)
    draw(cr)
    surf.flush()
    return any(b != 0 for b in surf.get_data())


def _wave():
    return (0.3 * np.sin(np.linspace(0, 20, 800))).astype(np.float32)


def test_waveform_draws_something():
    assert _has_ink(lambda cr: S.draw_waveform(cr, 200, 120, _wave(), 0.6, (0.3, 0.7, 0.96), 0.5, 1.0))


def test_bars_draw_something():
    spec = np.linspace(0.1, 1.0, 20).astype(np.float32)
    assert _has_ink(lambda cr: S.draw_bars(cr, 200, 120, spec, (0.3, 0.7, 0.96), 0.5))


def test_radial_draws_something():
    assert _has_ink(lambda cr: S.draw_radial(cr, 200, 120, _wave(), 0.6, (0.3, 0.7, 0.96), 0.5, 1.0))


def test_draw_with_backing_off_still_draws_the_visualization():
    spec = np.linspace(0.1, 1.0, 20).astype(np.float32)
    assert _has_ink(lambda cr: S.draw_bars(cr, 200, 120, spec, (0.3, 0.7, 0.96), 0.0))


def test_empty_data_does_not_crash():
    # The service may draw a frame before any audio has arrived.
    _has_ink(lambda cr: S.draw_waveform(cr, 200, 120, [], 0.0, (0.3, 0.7, 0.96), 0.5, 1.0))
    _has_ink(lambda cr: S.draw_bars(cr, 200, 120, [], (0.3, 0.7, 0.96), 0.5))
    _has_ink(lambda cr: S.draw_radial(cr, 200, 120, [], 0.0, (0.3, 0.7, 0.96), 0.5, 1.0))

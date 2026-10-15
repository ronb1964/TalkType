"""Type at pause: the meter, upstream's SegmentedVUMeter with the room level
and the speech threshold marked on it."""
import cairo

from tuxtalk.prefs import PauseMeter, SegmentedVUMeter


def pixel(surface, x, y):
    """(r, g, b) of one pixel of an ARGB32 surface, 0-255."""
    surface.flush()
    data = surface.get_data()
    i = y * surface.get_stride() + x * 4
    b, g, r = data[i], data[i + 1], data[i + 2]
    return r, g, b


def test_it_is_the_mic_tests_meter():
    assert issubclass(PauseMeter, SegmentedVUMeter)


def test_show_snapshot_sets_level_and_marks():
    m = PauseMeter()
    m.show_snapshot(0.5, 0.25, 0.75)
    assert m.level == 0.5 and m.room == 0.25 and m.threshold == 0.75


def test_marks_are_drawn_where_they_belong():
    m = PauseMeter()
    m.show_snapshot(0.0, 0.25, 0.75)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 20)
    cr = cairo.Context(surface)
    m._draw_marks(cr, 200, 20)
    r, g, b = pixel(surface, 150, 10)       # the threshold mark: #04B503
    assert g > 150 and r < 60 and b < 60
    r, g, b = pixel(surface, 50, 10)        # the room mark: grey
    assert abs(r - g) < 20 and abs(g - b) < 20 and r > 100


def test_a_cut_flashes_briefly():
    m = PauseMeter()
    m.show_snapshot(0.3, 0.1, 0.2, cut=True)
    assert m.flashing()
    m._flash_until = 0.0
    assert not m.flashing()

"""The recording indicator lets clicks through to the window underneath.

input_shape_combine_region(None) removes the input shape instead of emptying
it, so the whole transparent indicator window would take the clicks meant for
the app underneath, right where the "follow the window" option puts it.
"""
import pathlib

from tuxtalk import recording_indicator as ri


def test_the_indicator_is_click_through():
    src = pathlib.Path(ri.__file__).read_text()
    assert "input_shape_combine_region(None)" not in src
    assert 'self.connect("realize", lambda w: w.input_shape_combine_region(cairo.Region()))' in src

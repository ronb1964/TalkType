"""Preferences' "What works with what?" window tells the truth (recommend.py).

Ron, 0.14.6 test: with Parakeet, Whisper, CPU, Vulkan and CUDA there were too
many choices to know which work together.
"""
import pytest

from tuxtalk import recommend as r
from tuxtalk import whisper_vulkan as wv
from tuxtalk.model_helper import OFFERED_MODELS


def test_every_offered_model_is_in_the_table_once():
    listed = [m for _, models, *_ in r.COMPATIBILITY for m in models]
    assert sorted(listed) == sorted(OFFERED_MODELS)


def test_the_vulkan_column_matches_what_really_runs_on_vulkan():
    for _, models, _cpu, vulkan, _cuda in r.COMPATIBILITY:
        for model in models:
            assert vulkan[0] == wv.supports_model(model), model


def test_parakeet_is_shown_not_working_on_cuda():
    row = next(row for row in r.COMPATIBILITY if r.PARAKEET in row[1])
    assert row[4][0] is False and "processor" in row[4][1]


def test_large_v3_is_shown_needing_a_graphics_card():
    row = next(row for row in r.COMPATIBILITY if "large-v3" in row[1])
    assert row[2][0] is False and row[3][0] and row[4][0]


@pytest.mark.parametrize("hw, slower, says", [
    (r.Hardware("NVIDIA GeForce RTX 4070 SUPER", True), False,
     "NVIDIA GeForce RTX 4070 SUPER, so all three columns work"),
    (r.Hardware("AMD graphics", False), False, "processor and Vulkan columns work here. CUDA needs"),
    (r.Hardware("Intel graphics", False), False, "Intel graphics, so the processor and Vulkan"),
    (r.Hardware("graphics card", False), False, "Your computer: a graphics card, so"),
    (r.Hardware(None, False), True, "graphics chip was slower than the processor"),
    (r.Hardware(None, True), True, "NVIDIA card, but your processor was faster"),
    (r.Hardware(None, True), False, "Vulkan isn't working on it"),
    (r.Hardware(None, False), False, "no graphics chip TalkType can use"),
])
def test_the_computer_line_fits_every_kind_of_computer(hw, slower, says):
    """Ron asked how the line reads on other computers: "graphics card" read
    as "Your computer: graphics card", and a chip that lost the speed check
    was called no graphics card at all."""
    assert says in r.this_computer(hw, slower)

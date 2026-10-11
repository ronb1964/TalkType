"""Preferences' "What works with what?" window tells the truth (recommend.py).

Ron, 0.14.6 test: with Parakeet, Whisper, CPU, Vulkan and CUDA there were too
many choices to know which work together.
"""
from talktype import recommend as r
from talktype import whisper_vulkan as wv
from talktype.model_helper import OFFERED_MODELS


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


def test_the_computer_line_fits_the_hardware():
    assert "all three" in r.this_computer(r.Hardware("NVIDIA GeForce RTX 4070 SUPER", True))
    amd = r.this_computer(r.Hardware("AMD graphics", False))
    assert "processor and Vulkan" in amd and "needs an NVIDIA" in amd
    assert "CUDA and the processor" in r.this_computer(r.Hardware(None, True))
    assert "processor column" in r.this_computer(r.Hardware(None, False))

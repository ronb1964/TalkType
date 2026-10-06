"""Choosing large-v3 at first run without an NVIDIA card tells the truth.

It used to say large-v3 was "not compatible with CPU-only or AMD/Intel GPU
systems", which stopped being true in 0.12.0 when it gained Vulkan.
"""
from talktype import welcome_dialog as wd


def test_amd_or_intel_with_vulkan_is_told_how(monkeypatch):
    monkeypatch.setattr("talktype.whisper_vulkan.is_offered", lambda: True)
    title, body = wd._large_v3_without_nvidia_message()
    assert "graphics card" in title
    assert "Vulkan (any GPU)" in body and "AMD or Intel" in body
    assert "not compatible" not in body
    assert "Parakeet" in body


def test_no_usable_graphics_points_to_parakeet(monkeypatch):
    monkeypatch.setattr("talktype.whisper_vulkan.is_offered", lambda: False)
    title, body = wd._large_v3_without_nvidia_message()
    assert "required" in title.lower()
    assert "Parakeet" in body and "processor" in body

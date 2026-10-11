"""The Device dropdown says what each choice really does.

CUDA used to appear only after Preferences → Advanced → Download CUDA
Libraries, so NVIDIA owners looking under Device never found it. Now it's
always listed on NVIDIA, with its download size until it's installed. And with
Parakeet it said "CUDA (GPU)" while Parakeet ran on the processor.
"""
import pytest

from talktype.prefs import device_label


def test_cuda_not_downloaded_names_the_download():
    assert device_label("cuda", "small", cuda_ready=False) == "CUDA (NVIDIA, 1.4 GB download)"


def test_cuda_installed_is_plain():
    assert device_label("cuda", "large-v3", cuda_ready=True) == "CUDA (NVIDIA)"


@pytest.mark.parametrize("ready", [True, False])
def test_cuda_with_parakeet_says_it_runs_on_the_processor(ready):
    assert "Parakeet runs on the processor" in device_label("cuda", "parakeet-v3", ready)


def test_cuda_with_parakeet_still_names_the_download():
    assert "1.4 GB" in device_label("cuda", "parakeet-v3", cuda_ready=False)
    assert "1.4 GB" not in device_label("cuda", "parakeet-v3", cuda_ready=True)


def test_other_devices_keep_their_names():
    from talktype.whisper_vulkan import DEVICE_LABEL
    assert device_label("cpu", "parakeet-v3", True) == "CPU"
    assert device_label("vulkan", "parakeet-v3", True) == DEVICE_LABEL

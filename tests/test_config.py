"""Tests for config module validation logic"""
import pytest
from talktype.config import Settings, validate_config


def test_valid_config():
    """Test that a valid configuration passes validation"""
    s = Settings(
        model="small",
        device="cpu",
        hotkey="F8",
        mode="hold",
        toggle_hotkey="F9"
    )
    # Should not raise
    validate_config(s)


def test_invalid_model():
    """Test that invalid model name fails validation"""
    s = Settings(model="invalid-model")
    with pytest.raises(SystemExit) as exc_info:
        validate_config(s)
    assert exc_info.value.code == 1


def test_invalid_device():
    """Test that invalid device fails validation"""
    s = Settings(device="gpu")  # Should be "cuda" not "gpu"
    with pytest.raises(SystemExit):
        validate_config(s)


def test_invalid_mode():
    """Test that invalid mode fails validation"""
    s = Settings(mode="press")  # Should be "hold" or "toggle"
    with pytest.raises(SystemExit):
        validate_config(s)


def test_invalid_injection_mode():
    """Test that invalid injection_mode fails validation"""
    s = Settings(injection_mode="invalid")
    with pytest.raises(SystemExit):
        validate_config(s)


def test_negative_timeout():
    """Test that negative timeout fails validation"""
    s = Settings(auto_timeout_minutes=-1)
    with pytest.raises(SystemExit):
        validate_config(s)


def test_zero_timeout():
    """Test that zero timeout fails validation"""
    s = Settings(auto_timeout_minutes=0)
    with pytest.raises(SystemExit):
        validate_config(s)


def test_empty_hotkey():
    """Test that empty hotkey passes validation (allowed during onboarding)."""
    s = Settings(hotkey="")
    # Empty hotkey is valid — the welcome dialog handles hotkey assignment
    validate_config(s)


def test_empty_toggle_hotkey_in_toggle_mode():
    """Test that empty toggle_hotkey passes even in toggle mode (allowed during onboarding)."""
    s = Settings(mode="toggle", toggle_hotkey="")
    # Empty toggle_hotkey is valid — set during onboarding
    validate_config(s)


def test_empty_toggle_hotkey_in_hold_mode():
    """Test that empty toggle_hotkey is OK when mode is hold"""
    s = Settings(mode="hold", toggle_hotkey="")
    # Should not raise (toggle_hotkey not used in hold mode)
    validate_config(s)


def test_all_valid_models():
    """Test that all documented valid models pass validation"""
    valid_models = [
        "tiny", "tiny.en",
        "base", "base.en",
        "small", "small.en",
        "medium", "medium.en",
        "large", "large-v1", "large-v2", "large-v3"
    ]
    for model in valid_models:
        s = Settings(model=model)
        validate_config(s)  # Should not raise


def test_valid_devices():
    """Test both valid device types"""
    for device in ["cpu", "cuda", "CPU", "CUDA"]:  # Case insensitive
        s = Settings(device=device)
        validate_config(s)  # Should not raise


def test_valid_modes():
    """Test both valid mode types"""
    for mode in ["hold", "toggle", "HOLD", "TOGGLE"]:  # Case insensitive
        s = Settings(mode=mode)
        validate_config(s)  # Should not raise


def test_valid_injection_modes():
    """Test both valid injection mode types"""
    for mode in ["type", "paste", "TYPE", "PASTE"]:  # Case insensitive
        s = Settings(injection_mode=mode)
        validate_config(s)  # Should not raise


def test_positive_timeout():
    """Test that positive timeouts are valid"""
    for minutes in [1, 5, 10, 30, 60]:
        s = Settings(auto_timeout_minutes=minutes)
        validate_config(s)  # Should not raise

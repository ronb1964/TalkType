"""Tests for cuda_helper module"""
import os
from unittest.mock import patch, Mock
from talktype.cuda_helper import (
    detect_nvidia_gpu,
    has_cuda_libraries,
    get_appdir_cuda_path,
    is_first_run,
    mark_first_run_complete
)


def test_get_appdir_cuda_path():
    """Test CUDA path returns expected location"""
    path = get_appdir_cuda_path()
    assert path.endswith(".local/share/TalkType/cuda")
    assert os.path.expanduser("~") in path


@patch('subprocess.run')
def test_detect_nvidia_gpu_found(mock_run):
    """Test GPU detection when nvidia-smi succeeds"""
    mock_run.return_value = Mock(returncode=0, stdout="NVIDIA GeForce RTX 3080\n")
    result = detect_nvidia_gpu()
    assert result == "NVIDIA GeForce RTX 3080"  # .strip() removes the newline


@patch('subprocess.run')
def test_detect_nvidia_gpu_not_found(mock_run):
    """Test GPU detection when nvidia-smi fails"""
    mock_run.return_value = Mock(returncode=1, stdout="")
    result = detect_nvidia_gpu()
    assert result is False


@patch('subprocess.run', side_effect=FileNotFoundError)
def test_detect_nvidia_gpu_no_nvidia_smi(mock_run):
    """Test GPU detection when nvidia-smi not installed"""
    result = detect_nvidia_gpu()
    assert result is False


@patch('subprocess.run')
def test_detect_nvidia_gpu_timeout(mock_run):
    """Test GPU detection handles timeout gracefully"""
    import subprocess
    mock_run.side_effect = subprocess.TimeoutExpired(cmd='nvidia-smi', timeout=5)
    result = detect_nvidia_gpu()
    assert result is False


def test_first_run_flag(tmp_path):
    """Test first run flag management"""
    flag_file = tmp_path / ".first_run_done"

    with patch('talktype.cuda_helper.os.path.expanduser') as mock_expand:
        mock_expand.return_value = str(tmp_path / ".local/share/TalkType/.first_run_done")

        # Should be first run initially
        with patch('os.path.exists', return_value=False):
            assert is_first_run() is True

        # After marking complete, should not be first run
        with patch('os.path.exists', return_value=True):
            assert is_first_run() is False


@patch('subprocess.run')
@patch('os.path.exists')
@patch('os.listdir')
def test_has_cuda_libraries_permission_error(mock_listdir, mock_exists, mock_run):
    """Test has_cuda_libraries handles permission errors gracefully"""
    # Mock ldconfig to fail (first check in has_cuda_libraries)
    import subprocess
    mock_run.side_effect = subprocess.TimeoutExpired(cmd='ldconfig', timeout=2)

    # Mock directory checks to raise PermissionError
    mock_exists.return_value = True
    mock_listdir.side_effect = PermissionError("Access denied")

    # Should not crash, should return False
    result = has_cuda_libraries()
    assert result is False


@patch('subprocess.run')
@patch('os.path.exists')
@patch('os.listdir')
def test_has_cuda_libraries_os_error(mock_listdir, mock_exists, mock_run):
    """Test has_cuda_libraries handles OS errors gracefully"""
    # Mock ldconfig to fail (first check in has_cuda_libraries)
    import subprocess
    mock_run.side_effect = subprocess.TimeoutExpired(cmd='ldconfig', timeout=2)

    # Mock directory checks to raise OSError
    mock_exists.return_value = True
    mock_listdir.side_effect = OSError("Disk error")

    # Should not crash, should return False
    result = has_cuda_libraries()
    assert result is False

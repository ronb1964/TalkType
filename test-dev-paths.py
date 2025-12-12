#!/usr/bin/env python3
"""
Test that dev mode and production use different paths.
"""
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_paths():
    """Test path separation between dev and production."""
    print("Testing TalkType Path Separation")
    print("="*50)
    print()

    # Test without DEV_MODE
    print("1. Production Mode (DEV_MODE not set):")
    os.environ.pop("DEV_MODE", None)

    # Force reimport to pick up new env
    import importlib
    import talktype.config
    importlib.reload(talktype.config)

    from talktype.config import CONFIG_PATH, get_data_dir
    from talktype.cuda_helper import get_appdir_cuda_path

    print(f"   Config:      {CONFIG_PATH}")
    print(f"   Data:        {get_data_dir()}")
    print(f"   CUDA:        {get_appdir_cuda_path()}")
    print()

    # Test with DEV_MODE
    print("2. Dev Mode (DEV_MODE=1):")
    os.environ["DEV_MODE"] = "1"

    # Force reimport
    importlib.reload(talktype.config)
    from talktype.config import CONFIG_PATH as CONFIG_PATH_DEV
    from talktype.config import get_data_dir as get_data_dir_dev

    # Reimport cuda_helper to pick up new paths
    import talktype.cuda_helper
    importlib.reload(talktype.cuda_helper)
    from talktype.cuda_helper import get_appdir_cuda_path as get_cuda_dev

    print(f"   Config:      {CONFIG_PATH_DEV}")
    print(f"   Data:        {get_data_dir_dev()}")
    print(f"   CUDA:        {get_cuda_dev()}")
    print()

    # Verify they're different
    print("3. Verification:")
    config_diff = "talktype-dev" in CONFIG_PATH_DEV and "talktype-dev" not in CONFIG_PATH
    data_diff = "TalkType-dev" in get_data_dir_dev() and "TalkType-dev" not in get_data_dir()
    cuda_diff = "TalkType-dev" in get_cuda_dev() and "TalkType-dev" not in get_appdir_cuda_path()

    print(f"   Config paths different:  {'✅' if config_diff else '❌'}")
    print(f"   Data paths different:    {'✅' if data_diff else '❌'}")
    print(f"   CUDA paths different:    {'✅' if cuda_diff else '❌'}")
    print()

    if config_diff and data_diff and cuda_diff:
        print("✅ SUCCESS: Dev and production use separate paths!")
        return True
    else:
        print("❌ FAILED: Paths are not properly separated!")
        return False

if __name__ == "__main__":
    success = test_paths()
    sys.exit(0 if success else 1)

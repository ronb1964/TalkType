"""Guard against version drift between pyproject.toml and __init__.py.

The AppImage filename comes from pyproject.toml (container-build.sh) while
the running app reports talktype.__version__ — if they diverge, the update
checker offers the app an 'update' to itself forever. This happened once
(commit da52655). This test makes the drift fail CI/local runs instead.
"""
import re
from pathlib import Path

from talktype import __version__


def test_versions_match():
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(), re.MULTILINE)
    assert m, "version not found in pyproject.toml"
    assert m.group(1) == __version__, (
        f"pyproject.toml says {m.group(1)} but talktype.__version__ is {__version__} — "
        "bump BOTH before building a release"
    )

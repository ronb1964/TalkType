import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe_env import parse_portal_version


def test_parses_fedora_version():
    assert parse_portal_version("1.22.1-1.fc44.x86_64") == (1, 22)


def test_parses_bare_version():
    assert parse_portal_version("1.21.0") == (1, 21)


def test_unknown_returns_zeroes():
    assert parse_portal_version("not-a-version") == (0, 0)

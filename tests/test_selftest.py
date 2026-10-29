"""Runs Bite's offline self-test (tests/selftest.py) under pytest. No key, no network.
Its "ok"/"FAIL" lines print as they run (pytest's -s is on in pyproject.toml), so a slow PC doesn't look frozen."""

import subprocess
import sys
from pathlib import Path


def test_selftest():
    r = subprocess.run([sys.executable, str(Path(__file__).with_name("selftest.py"))])
    assert r.returncode == 0, "a self-test check failed: see the FAIL lines above"

"""Runs Bite's offline self-test (tests/selftest.py) under pytest. No key, no network."""

import subprocess
import sys
from pathlib import Path


def test_selftest():
    r = subprocess.run([sys.executable, str(Path(__file__).with_name("selftest.py"))],
                       capture_output=True, text=True)
    fails = [line for line in r.stdout.splitlines() if line.startswith("FAIL")]
    assert r.returncode == 0, "\n".join(fails) or r.stdout[-2000:] + r.stderr[-2000:]

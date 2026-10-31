"""Where Bite makes its copies of a JavaScript project. No network."""

import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).parent.parent
sys.path.insert(0, str(KIT))

import repo  # noqa: E402


def test_node_copies_are_not_in_a_hidden_folder(tmp_path):
    # Copies go inside node_modules/ so Node finds the project's packages. A folder named with a leading dot made
    # Express's tests fail there: its static file server refuses any path with a dot-folder in it (60 tests).
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "node_modules").mkdir()
    old = tempfile.tempdir
    try:
        repo.load_cfg(tmp_path)
        tmp = Path(tempfile.tempdir).resolve()
    finally:
        tempfile.tempdir = old
    inside = tmp.relative_to((tmp_path / "node_modules").resolve())
    assert inside.parts and not any(p.startswith(".") for p in inside.parts), inside

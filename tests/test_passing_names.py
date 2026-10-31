"""A passing test whose name has a failure word in it. No network."""

import sys
from pathlib import Path

KIT = Path(__file__).parent.parent
sys.path.insert(0, str(KIT))

import bite  # noqa: E402


def run_printing(tmp_path, lines):
    script = tmp_path / "fake_tests.py"
    script.write_text("print(" + repr("\n".join(lines)) + ")\n", encoding="utf-8")
    ini = tmp_path / "kit.ini"
    ini.write_text(f'[kit]\nproject_folder = {tmp_path}\ntest_command = "{sys.executable}" "{script}"\n',
                   encoding="utf-8")
    cfg = bite.Config(ini)
    return bite.run_tests(cfg, tmp_path)


def test_passing_test_named_parse_error_is_not_a_failure(tmp_path):
    # expressjs/express has "✔ should persist store when parse error": a pass, which Bite read as a failure.
    r = run_printing(tmp_path, ["  session", "    ✔ should persist store when parse error", "", "  1290 passing (4s)"])
    assert r["ok"], r["why"]


def test_a_real_parse_error_still_fails(tmp_path):
    r = run_printing(tmp_path, ["res://main.gd:3 - Parse Error: Expected end of statement"])
    assert not r["ok"]

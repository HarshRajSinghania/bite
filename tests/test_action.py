"""Runs the pull request check's own script from action.yml with a stand-in `bite`, so the check's color is tested
against what the comment says. Needs bash and git; no network."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).parent.parent
BASH = shutil.which("bash")


def action_script():
    lines = (KIT / "action.yml").read_text(encoding="utf-8").splitlines()
    start = max(i for i, ln in enumerate(lines) if ln.strip() == "run: |") + 1
    return "\n".join(ln[8:] for ln in lines[start:])


def run_check(tmp_path, heading, report=False):
    repo = tmp_path / "repo"
    repo.mkdir()
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout.strip()  # noqa: E731
    git("init", "-q")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "base")
    base = git("rev-parse", "HEAD")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "change")
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "bite.py").write_text(
        "import pathlib\n"
        "p = pathlib.Path('bite_proof'); p.mkdir(exist_ok=True)\n"
        f"(p / 'COMMENT.md').write_text('<!-- bite-check -->\\n### {heading}\\n', encoding='utf-8')\n"
        + ("(p / 'FREE_REPORT.md').write_text('gap', encoding='utf-8')\n" if report else ""))
    (fake / "bite").write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "{(fake / "bite.py").as_posix()}"\n')
    (fake / "bite").chmod(0o755)
    env = dict(os.environ, PATH=f"{fake}{os.pathsep}{os.environ['PATH']}", BASE=base, MAX="20", ARGS="", FAIL="true",
               COMMENT="false", PR="1", GITHUB_STEP_SUMMARY=str(tmp_path / "summary.md"))
    return subprocess.run([BASH, "-e", "-o", "pipefail", "-c", action_script()], cwd=repo, env=env,
                          capture_output=True, text=True)


@pytest.mark.skipif(not BASH or os.name == "nt", reason="needs bash (the check runs on Linux)")
def test_tests_already_failing_turn_the_check_red(tmp_path):
    r = run_check(tmp_path, "❌ Bite: your tests already fail")
    assert r.returncode == 1 and "couldn't check it" in r.stdout


@pytest.mark.skipif(not BASH or os.name == "nt", reason="needs bash (the check runs on Linux)")
def test_a_green_comment_keeps_the_check_green(tmp_path):
    r = run_check(tmp_path, "✅ Bite-proof. Nice work.")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(not BASH or os.name == "nt", reason="needs bash (the check runs on Linux)")
def test_a_gap_still_turns_the_check_red(tmp_path):
    r = run_check(tmp_path, "⚠️ Bite: no test noticed 1 change", report=True)
    assert r.returncode == 1 and "isn't guarded" in r.stdout


@pytest.mark.skipif(not BASH or os.name == "nt", reason="needs bash (the check runs on Linux)")
def test_write_tests_without_a_key_runs_the_free_check_only(tmp_path, monkeypatch):
    monkeypatch.setenv("WRITE", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = run_check(tmp_path, "✅ Bite-proof. Nice work.")
    assert r.returncode == 0 and "no anthropic-api-key" in r.stdout, r.stdout + r.stderr

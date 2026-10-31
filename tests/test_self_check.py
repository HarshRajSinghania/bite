"""bot/self_check.py, Bite checking Bite, against a stand-in `gh` that records each call and answers like GitHub.
No network. Skipped on Windows: the step runs on GitHub's Linux runners."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the workflow runs on Linux")
KIT = Path(__file__).parent.parent

FAKE_GH = r'''
import json, os, sys
a = sys.argv[1:]
method, path = a[a.index("-X") + 1], a[a.index("-X") + 2]
body = json.loads(sys.stdin.read()) if "--input" in a else None
with open(os.environ["GH_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps([method, path, body]) + "\n")
fail = os.environ.get("GH_FAIL", "")
if fail and fail in f"{method} {path}":
    print("HTTP 403: GitHub Actions is not permitted to create or approve pull requests.")
    sys.exit(1)
if method == "GET" and "/issues?" in path:
    print(json.dumps(json.loads(os.environ.get("GH_ISSUES", "[]"))))
elif method == "GET" and "/pulls?" in path:
    print(os.environ.get("GH_PULLS", "[]"))
elif method == "POST" and path.endswith("/issues"):
    print(json.dumps({"number": 70}))
elif path.endswith("/git/commits/mainsha"):
    print(json.dumps({"tree": {"sha": "basetree"}}))
elif path.endswith("/git/trees"):
    print(json.dumps({"sha": "newtree"}))
elif path.endswith("/git/commits"):
    print(json.dumps({"sha": "newcommit"}))
elif path.endswith("/git/refs"):
    print(json.dumps({"ref": body["ref"]}))
elif method == "POST" and path.endswith("/pulls"):
    print(json.dumps({"number": 71}))
'''

REPORT = """# Bite: changes no test noticed

## 1. 1a2b3c4d Say why pytest crashed

- What Bite saw: no test noticed it was gone
"""


def run(tmp_path, report=REPORT, test=True, **env):
    work = tmp_path / "work"
    (work / "bite_proof").mkdir(parents=True)
    if report:
        (work / "bite_proof" / "FREE_REPORT.md").write_text(report, encoding="utf-8")
    if test:
        (work / "bite_proof" / "missing_tests" / "tests").mkdir(parents=True)
        (work / "bite_proof" / "missing_tests" / "tests" / "test_bite_claim.py").write_text("def test_x():\n    pass\n")
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "gh.py").write_text(FAKE_GH)
    (fake / "gh").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake / "gh.py"}" "$@"\n')
    (fake / "gh").chmod(0o755)
    log = tmp_path / "gh.log"
    e = dict(os.environ, PATH=f"{fake}{os.pathsep}{os.environ['PATH']}", GH_LOG=str(log), GITHUB_REPOSITORY="o/bite",
             GITHUB_SHA="mainsha", **env)
    r = subprocess.run([sys.executable, str(KIT / "bot" / "self_check.py")], cwd=work, env=e, capture_output=True,
                       text=True)
    calls = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return r, calls


def posted(calls, end):
    return next(b for m, p, b in calls if m == "POST" and p.endswith(end))


def test_a_gap_opens_an_issue_then_a_pull_request_that_closes_it(tmp_path):
    r, calls = run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    issue = posted(calls, "/issues")
    assert "no test noticed" in issue["title"] and "1a2b3c4d Say why pytest crashed" in issue["body"]
    assert "<!-- bite-self-check: 1a2b3c4d -->" in issue["body"]
    commit = posted(calls, "/git/commits")
    assert commit["parents"] == ["mainsha"] and "Closes #70" in commit["message"]
    assert posted(calls, "/git/trees")["tree"][0]["path"] == "tests/test_bite_claim.py"
    assert posted(calls, "/git/refs") == {"ref": "refs/heads/bite/self-check-70", "sha": "newcommit"}
    pr = posted(calls, "/pulls")
    assert pr["base"] == "main" and pr["head"] == "bite/self-check-70" and pr["body"].startswith("Closes #70.")
    # The issue comes first, so the pull request can close it.
    order = [p for m, p, b in calls if m == "POST"]
    assert order.index("repos/o/bite/issues") < order.index("repos/o/bite/pulls")
    # A workflow's pull request gets no checks by itself; main needs them to merge.
    assert posted(calls, "/actions/workflows/tests.yml/dispatches") == {"ref": "bite/self-check-70"}


OLD = "old\n<!-- bite-self-check: 1a2b3c4d -->\n"


def test_a_gap_already_reported_is_not_reported_again(tmp_path):
    r, calls = run(tmp_path, GH_ISSUES=json.dumps([{"number": 60, "state": "closed", "body": OLD}]))
    assert r.returncode == 0 and "Nothing new" in r.stdout
    assert not [c for c in calls if c[0] == "POST"]


def test_without_a_key_an_open_issue_gets_nothing_new(tmp_path):
    r, calls = run(tmp_path, test=False, GH_ISSUES=json.dumps([{"number": 60, "state": "open", "body": OLD}]))
    assert r.returncode == 0 and "Nothing new" in r.stdout
    assert not [c for c in calls if c[0] == "POST"]


def test_an_open_issue_gets_its_pull_request_once_the_test_is_written(tmp_path):
    # The first run had no key (issue only); the key came later, so this run wrote the test.
    issues = json.dumps([{"number": 60, "state": "open", "body": OLD}, {"number": 61, "pull_request": {}, "body": OLD}])
    r, calls = run(tmp_path, GH_ISSUES=issues)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "repos/o/bite/issues" not in [p for m, p, b in calls if m == "POST"]
    assert "Closes #60" in posted(calls, "/git/commits")["message"]
    pr = posted(calls, "/pulls")
    assert pr["head"] == "bite/self-check-60" and pr["body"].startswith("Closes #60.")


def test_an_open_issue_that_already_has_its_pull_request_gets_no_second_one(tmp_path):
    r, calls = run(tmp_path, GH_ISSUES=json.dumps([{"number": 60, "state": "open", "body": OLD}]),
                   GH_PULLS='[{"number": 62}]')
    assert r.returncode == 0 and "already opened a pull request for #60" in r.stdout
    assert not [c for c in calls if c[0] == "POST"]


def test_without_a_key_it_opens_the_issue_only(tmp_path):
    r, calls = run(tmp_path, test=False)
    assert r.returncode == 0
    assert "ANTHROPIC_API_KEY" in posted(calls, "/issues")["body"]
    assert [p for m, p, b in calls if m == "POST"] == ["repos/o/bite/issues"]


def test_no_gap_opens_nothing(tmp_path):
    r, calls = run(tmp_path, report="", test=False)
    assert r.returncode == 0 and not calls


def test_when_the_pull_request_is_refused_the_issue_still_stands(tmp_path):
    r, calls = run(tmp_path, GH_FAIL="POST repos/o/bite/pulls")
    assert r.returncode == 0 and "Bite opened issue #70" in r.stdout
    assert "Allow GitHub Actions to create and approve pull requests" in r.stdout

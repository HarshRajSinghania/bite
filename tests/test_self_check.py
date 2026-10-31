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

# A tiny repo like Bite's: a fix in calc.py that no test noticed, and the test Bite wrote for it.
CALC = "def clamp(x, lo, hi):\n    return min(x, hi)\n"
FIXED = "def clamp(x, lo, hi):\n    return max(lo, min(x, hi))\n"
NOTICES = ("import sys\nfrom pathlib import Path\n\nsys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n"
           "from calc import clamp\n\n\ndef test_low():\n    assert clamp(-5, 0, 9) == 0\n")
GIT = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
           GIT_AUTHOR_DATE="2026-01-01T00:00:00Z", GIT_COMMITTER_DATE="2026-01-01T00:00:00Z")


def make_repo(work):
    """Fixed dates and names, so the fix commit's sha is the same every time."""
    e = dict(os.environ, **GIT)
    g = lambda *a: subprocess.run(["git", *a], cwd=work, env=e, check=True, capture_output=True, text=True).stdout  # noqa: E731
    g("init", "-q")
    (work / "calc.py").write_text(CALC)
    g("add", "calc.py")
    g("commit", "-q", "-m", "calc")
    (work / "calc.py").write_text(FIXED)
    g("commit", "-q", "-am", "Fix clamp below lo")
    return g("rev-parse", "HEAD")[:8]


def fix_sha():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        return make_repo(Path(d))


S = fix_sha()

REPORT = f"""# Bite: changes no test noticed

## 1. {S} Fix clamp below lo

- What Bite saw: no test noticed it was gone
"""


def run(tmp_path, report=REPORT, test=True, existing=False, written=NOTICES, **env):
    work = tmp_path / "work"
    work.mkdir()
    assert make_repo(work) == S
    (work / "bite_proof").mkdir()
    if existing:  # an earlier self-check's test, already in the repo under the name Bite uses each time
        (work / "tests").mkdir()
        (work / "tests" / "test_bite_claim.py").write_text("def test_old():\n    pass\n")
    if report:
        (work / "bite_proof" / "FREE_REPORT.md").write_text(report, encoding="utf-8")
    if test:
        (work / "bite_proof" / "missing_tests" / "tests").mkdir(parents=True)
        (work / "bite_proof" / "missing_tests" / "tests" / "test_bite_claim.py").write_text(written)
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
    assert "no test noticed" in issue["title"] and f"{S} Fix clamp below lo" in issue["body"]
    assert f"<!-- bite-self-check: {S} -->" in issue["body"]
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


OLD = f"old\n<!-- bite-self-check: {S} -->\n"


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


def test_a_test_from_an_earlier_self_check_is_not_replaced(tmp_path):
    r, calls = run(tmp_path, existing=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert posted(calls, "/git/trees")["tree"][0]["path"] == "tests/test_bite_claim_70.py"
    assert "`tests/test_bite_claim_70.py`" in posted(calls, "/pulls")["body"]


def test_bites_own_test_is_held_to_bites_own_question_and_shown_as_a_check(tmp_path):
    r, calls = run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"fails when {S} is taken out, checked on today's main" in posted(calls, "/pulls")["body"]
    status = next(b for m, p, b in calls if m == "POST" and "/statuses/" in p)
    assert status["state"] == "success" and status["context"] == "Bite / own test" and S in status["description"]
    assert ["POST", "repos/o/bite/statuses/newcommit"] in [[m, p] for m, p, b in calls]


def test_a_test_that_doesnt_notice_the_change_gets_no_pull_request(tmp_path):
    r, calls = run(tmp_path, written="def test_nothing():\n    assert True\n")
    assert r.returncode == 0 and "doesn't notice" in r.stdout and "still passes with the change taken out" in r.stdout
    assert "repos/o/bite/issues" in [p for m, p, b in calls if m == "POST"]  # the issue still stands
    assert not [c for c in calls if c[1].endswith("/pulls") and c[0] == "POST"]


def test_when_the_code_has_moved_on_it_asks_at_the_gaps_own_commit(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    make_repo(work)
    e = dict(os.environ, **GIT)
    (work / "calc.py").write_text("def clamp(x, lo, hi):\n    # keep x in [lo, hi]\n    return max(lo, min(x, hi))\n")
    subprocess.run(["git", "commit", "-q", "-am", "comment"], cwd=work, env=e, check=True)
    sys.path.insert(0, str(KIT / "bot"))
    import self_check
    cwd = os.getcwd()
    os.chdir(work)
    try:
        assert self_check.notices(S, "test_bite_claim.py", NOTICES) == (True, "its own commit (the code has changed since)")
        assert self_check.notices(S, "test_bite_claim.py", "def test_nothing():\n    pass\n")[0] is False
    finally:
        os.chdir(cwd)

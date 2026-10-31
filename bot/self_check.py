"""Bite checks Bite. Run by .github/workflows/self-check.yml after `bite --free` has run on this repo's own commits.

When Bite found a change in Bite that no test noticed (bite_proof/FREE_REPORT.md), it opens one issue about it.
When it also wrote the missing test (--write-tests, bite_proof/missing_tests/), it opens a pull request into main
that adds the test and closes the issue, then starts the tests workflow on it: GitHub doesn't start checks on a pull
request a workflow opened, and main needs them green to merge.

Uses the workflow's own token through the `gh` command (contents, issues, pull-requests and actions write), never
the bite-check app's. A gap Bite has reported once (open or closed issue) is never reported again; while its issue
is still open, a later run that writes the test (say the key was added since) opens the pull request for it.
Before it opens the pull request, Bite holds its own test to its own question, on today's main (or, if the code has
moved on so the change no longer comes out cleanly, at the gap's own commit): with the test in, it passes, and with
the gap's change taken out, it fails. Then it puts that result on the pull request as
a check ("Bite / own test"). A test that doesn't notice gets no pull request.
Standard library only.
"""

import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from open_pr import api  # noqa: E402  the same small `gh api` wrapper the Action's open-pr step uses

REPORT = Path("bite_proof/FREE_REPORT.md")
TESTS = Path("bite_proof/missing_tests")
MARK = "<!-- bite-self-check: {} -->"


def gaps(report: str) -> list:
    """(short sha, commit title) of each change no test noticed, as the free report lists them."""
    return re.findall(r"^## \d+\. ([0-9a-f]{8}) (.*)$", report, re.M)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def pytest(folder: Path, rel: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", rel], cwd=folder,
                          capture_output=True, text=True, timeout=600)


def notices(sha: str, rel: str, test: str, at: str = "HEAD"):
    """Bite's own question, asked of its own test: on a copy of `at` with the test in, it passes; with the change
    `sha` made to the code taken back out, it fails (pytest's "tests failed", not a load error). Asked of today's
    code first; when the code has moved on so the change no longer comes out cleanly, at the gap's own commit.
    The copy comes from `git archive`, so this checkout is never touched.
    (True, where it was checked) or (False, why it doesn't notice)."""
    code = [f for f in git("diff", "--name-only", f"{sha}^", sha).split()
            if f.endswith(".py") and not f.startswith("tests/") and "/tests/" not in f]
    if not code:
        return False, "the change has no Python code outside tests/ to take out"
    where = "today's main" if at == "HEAD" else "its own commit (the code has changed since)"
    tmp = Path(tempfile.mkdtemp(prefix="bite_own_"))
    try:
        tar = tmp / "copy.tar"
        git("archive", "--format=tar", "-o", str(tar), at)
        with tarfile.open(tar) as t:
            t.extractall(tmp / "copy", filter="data") if hasattr(tarfile, "data_filter") else t.extractall(tmp / "copy")
        copy = tmp / "copy"
        (copy / rel).parent.mkdir(parents=True, exist_ok=True)
        (copy / rel).write_text(test, encoding="utf-8")
        if pytest(copy, rel).returncode != 0:
            return False, f"it fails on {where} even with the change in"
        undo = subprocess.run(["git", "apply", "-R"], input=git("diff", f"{sha}^", sha, "--", *code), cwd=copy,
                              capture_output=True, text=True)
        if undo.returncode:
            if at == "HEAD":
                return notices(sha, rel, test, at=sha)
            return False, f"the change can't be taken out ({undo.stderr.strip()[:200]})"
        rc = pytest(copy, rel).returncode
        if rc == 1:
            return True, where
        return False, ("it still passes with the change taken out" if rc == 0
                       else f"it doesn't load without the change (pytest exit {rc})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def reported(repo: str) -> list:
    """Every self-check issue so far, open or closed, so a gap is reported once (GitHub lists pull requests too)."""
    found = api("GET", f"repos/{repo}/issues?state=all&per_page=100&creator=github-actions%5Bbot%5D") or []
    return [i for i in found if "pull_request" not in i]


def main() -> int:
    if not REPORT.is_file():
        print("Bite: every change Bite checked in itself had a test that noticed it. Nothing to open.")
        return 0
    report = REPORT.read_text(encoding="utf-8")
    found = gaps(report)
    if not found:
        return 0
    repo, main_sha = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"]
    files = sorted(p.relative_to(TESTS).as_posix() for p in TESTS.rglob("*") if p.is_file()) if TESTS.is_dir() else []
    issues = reported(repo)
    owner = lambda sha: next((i for i in issues if MARK.format(sha) in (i.get("body") or "")), None)  # noqa: E731
    new = [(sha, title) for sha, title in found if not owner(sha)]
    # A gap whose issue is still open gets its pull request now, if this run wrote the test (say the key came later).
    still_open = sorted({owner(sha)["number"] for sha, _ in found if owner(sha) and owner(sha).get("state") == "open"})
    closes = []
    if new:
        one = len(new) == 1
        body = (f"Bite checked its own recent commits and found {'a change' if one else f'{len(new)} changes'} that no "
                "test noticed: with the change taken out, every test still passed.\n\n"
                + "\n".join(f"- {sha} {title}" for sha, title in new) + "\n\n"
                + ("Bite also wrote the missing test and will open a pull request with it that closes this issue."
                   if files else "To have Bite write the missing test too, add the repository secret ANTHROPIC_API_KEY.")
                + "\n\n<details><summary>Bite's report</summary>\n\n" + report[:50000] + "\n</details>\n\n"
                + "\n".join(MARK.format(sha) for sha, _ in new) + "\n")
        issue = api("POST", f"repos/{repo}/issues", {
            "title": f"Bite found {'a change' if one else f'{len(new)} changes'} in Bite that no test noticed",
            "body": body})["number"]
        print(f"Bite opened issue #{issue}.")
        closes.append(issue)
    if not files:
        if not new:
            print("Bite: it already opened an issue about each gap it found. Nothing new.")
        return 0
    closes += still_open
    if not closes:
        print("Bite: each gap it wrote a test for already has a closed issue. Nothing new.")
        return 0
    issue = closes[0]
    # Bite's own bar: each test must fail when one of this run's gaps is taken out (on today's main if it can be).
    shas = [sha for sha, _ in found]
    held = {}
    for f in files:
        why = []
        for sha in shas:
            ok, r = notices(sha, f, (TESTS / f).read_text(encoding="utf-8"))
            if ok:
                held[f] = (sha, r)
                break
            why.append(f"{sha}: {r}")
        if f not in held:
            print(f"::warning::Bite didn't open a pull request for #{issue}: its test `{f}` doesn't notice the change "
                  f"taken out ({'; '.join(why)}).")
            return 0
    branch = f"bite/self-check-{issue}"
    if api("GET", f"repos/{repo}/pulls?state=all&head={quote(repo.split('/')[0])}:{quote(branch, safe='')}"):
        print(f"Bite: it already opened a pull request for #{issue}. Nothing new.")
        return 0
    shut = ", ".join(f"closes #{n}" for n in closes)
    shut = shut[0].upper() + shut[1:]
    it = "it" if len(files) == 1 else "them"
    # Bite names its tests the same way each time (tests/test_bite_claim.py): one already in the repo, from an
    # earlier self-check, gets this issue's number in the new one's name instead of being replaced.
    where = {f: f if not Path(f).exists() else re.sub(r"(\.[^./]+)?$", lambda m: f"_{issue}{m.group(1) or ''}", f, count=1)
             for f in files}
    try:
        tree = api("GET", f"repos/{repo}/git/commits/{main_sha}")["tree"]["sha"]
        tree = api("POST", f"repos/{repo}/git/trees", {"base_tree": tree, "tree": [
            {"path": where[f], "mode": "100644", "type": "blob", "content": (TESTS / f).read_text(encoding="utf-8")}
            for f in files]})["sha"]
        commit = api("POST", f"repos/{repo}/git/commits", {
            "message": f"Add the missing test{'' if len(files) == 1 else 's'} Bite wrote for itself\n\n"
                       "Bite ran each one: it passes with the change and fails with the change taken out.\n\n"
                       f"{shut}",
            "tree": tree, "parents": [main_sha]})["sha"]
        api("POST", f"repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": commit})
        pr = api("POST", f"repos/{repo}/pulls", {
            "title": f"Bite: add the missing test{'' if len(files) == 1 else 's'} Bite wrote for itself",
            "head": branch, "base": "main",
            "body": f"{shut}.\n\nBite wrote {'this test' if len(files) == 1 else 'these tests'} for a "
                    f"change in Bite that no test noticed, and ran {it} itself: {'it passes' if len(files) == 1 else 'each passes'} "
                    "with the change and fails with the change taken out.\n\n"
                    + "\n".join(f"- `{where[f]}`: fails when {held[f][0]} is taken out, checked on {held[f][1]}" for f in files)})["number"]
    except (RuntimeError, KeyError, TypeError) as e:
        print(f"::warning::Bite couldn't open the pull request with {it} for #{issue} (the workflow needs "
              "contents and pull-requests write, and Settings, Actions, General: \"Allow GitHub Actions to create and "
              f"approve pull requests\"): {e}")
        return 0
    print(f"Bite opened #{pr} with {it}.")
    try:  # the same result as a check on the pull request, where a reviewer looks first
        api("POST", f"repos/{repo}/statuses/{commit}", {
            "state": "success", "context": "Bite / own test",
            "description": ("; ".join(f"{Path(where[f]).name} fails when {held[f][0]} is taken out" for f in files))[:140]})
    except RuntimeError as e:
        print(f"::warning::Bite couldn't put its own check on #{pr} (the workflow needs statuses: write): {e}")
    try:  # a workflow_dispatch is the one start a workflow's token may give: the checks main needs then run
        api("POST", f"repos/{repo}/actions/workflows/tests.yml/dispatches", {"ref": branch})
    except RuntimeError as e:
        print(f"::warning::Bite couldn't start the tests on #{pr} (the workflow needs actions: write): {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

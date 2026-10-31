"""Bite checks Bite. Run by .github/workflows/self-check.yml after `bite --free` has run on this repo's own commits.

When Bite found a change in Bite that no test noticed (bite_proof/FREE_REPORT.md), it opens one issue about it.
When it also wrote the missing test (--write-tests, bite_proof/missing_tests/), it opens a pull request into main
that adds the test and closes the issue, then starts the tests workflow on it: GitHub doesn't start checks on a pull
request a workflow opened, and main needs them green to merge.

Uses the workflow's own token through the `gh` command (contents, issues, pull-requests and actions write), never
the bite-check app's. A gap Bite has reported once (open or closed issue) is never reported again.
Standard library only.
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from open_pr import api  # noqa: E402  the same small `gh api` wrapper the Action's open-pr step uses

REPORT = Path("bite_proof/FREE_REPORT.md")
TESTS = Path("bite_proof/missing_tests")
MARK = "<!-- bite-self-check: {} -->"


def gaps(report: str) -> list:
    """(short sha, commit title) of each change no test noticed, as the free report lists them."""
    return re.findall(r"^## \d+\. ([0-9a-f]{8}) (.*)$", report, re.M)


def reported(repo: str) -> str:
    """Every self-check issue body so far, open or closed, so a gap is reported once."""
    found = api("GET", f"repos/{repo}/issues?state=all&per_page=100&creator=github-actions%5Bbot%5D") or []
    return "\n".join(i.get("body") or "" for i in found)


def main() -> int:
    if not REPORT.is_file():
        print("Bite: every change Bite checked in itself had a test that noticed it. Nothing to open.")
        return 0
    report = REPORT.read_text(encoding="utf-8")
    found = gaps(report)
    if not found:
        return 0
    repo, main_sha = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"]
    seen = reported(repo)
    new = [(sha, title) for sha, title in found if MARK.format(sha) not in seen]
    if not new:
        print("Bite: it already opened an issue about each gap it found. Nothing new.")
        return 0
    files = sorted(p.relative_to(TESTS).as_posix() for p in TESTS.rglob("*") if p.is_file()) if TESTS.is_dir() else []
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
    if not files:
        return 0
    it = "it" if len(files) == 1 else "them"
    branch = f"bite/self-check-{issue}"
    try:
        tree = api("GET", f"repos/{repo}/git/commits/{main_sha}")["tree"]["sha"]
        tree = api("POST", f"repos/{repo}/git/trees", {"base_tree": tree, "tree": [
            {"path": f, "mode": "100644", "type": "blob", "content": (TESTS / f).read_text(encoding="utf-8")}
            for f in files]})["sha"]
        commit = api("POST", f"repos/{repo}/git/commits", {
            "message": f"Add the missing test{'' if len(files) == 1 else 's'} Bite wrote for itself\n\n"
                       "Bite ran each one: it passes with the change and fails with the change taken out.\n\n"
                       f"Closes #{issue}",
            "tree": tree, "parents": [main_sha]})["sha"]
        api("POST", f"repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": commit})
        pr = api("POST", f"repos/{repo}/pulls", {
            "title": f"Bite: add the missing test{'' if len(files) == 1 else 's'} Bite wrote for itself",
            "head": branch, "base": "main",
            "body": f"Closes #{issue}.\n\nBite wrote {'this test' if len(files) == 1 else 'these tests'} for a "
                    f"change in Bite that no test noticed, and ran {it} itself: {'it passes' if len(files) == 1 else 'each passes'} "
                    "with the change and fails with the change taken out.\n\n"
                    + "\n".join(f"- `{f}`" for f in files)})["number"]
    except (RuntimeError, KeyError, TypeError) as e:
        print(f"::warning::Bite opened issue #{issue} but couldn't open the pull request with {it} (the workflow needs "
              "contents and pull-requests write, and Settings, Actions, General: \"Allow GitHub Actions to create and "
              f"approve pull requests\"): {e}")
        return 0
    print(f"Bite opened #{pr} with {it}.")
    try:  # a workflow_dispatch is the one start a workflow's token may give: the checks main needs then run
        api("POST", f"repos/{repo}/actions/workflows/tests.yml/dispatches", {"ref": branch})
    except RuntimeError as e:
        print(f"::warning::Bite couldn't start the tests on #{pr} (the workflow needs actions: write): {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

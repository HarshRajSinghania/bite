"""Offline checks for recent.py: a scripted worker and judge, a tiny repo with Claude-made commits.
Run: python tests/selftest.py, or python -m pytest   (no key, no network)"""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
import recent  # noqa: E402

PY = sys.executable
print("Bite self-test: about 50 checks on small practice repos, 15 s to 3 min. Each \"ok\" line is one check.",
      flush=True)
CLAUDE = "\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + name, flush=True)


def sh(root, *a):
    subprocess.run(a, cwd=root, check=True, capture_output=True)


def commit(root, msg):
    sh(root, "git", "add", "-A")
    sh(root, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg)


def make_repo():
    root = Path(tempfile.mkdtemp()) / "proj"
    root.mkdir()
    sh(root, "git", "init", "-q")
    (root / "calc.py").write_text("def clamp(x, lo, hi):\n    return x\n")
    (root / "test_calc.py").write_text("import unittest\nfrom calc import clamp\n\nclass T(unittest.TestCase):\n"
                                       "    def test_mid(self):\n        self.assertEqual(clamp(5, 0, 9), 5)\n")
    (root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m unittest -q\nallowed_programs = {PY}\n")
    commit(root, "start")
    # Claims both ends; only the low end is done, and no test was added.
    (root / "calc.py").write_text("def clamp(x, lo, hi):\n    if x < lo:\n        return lo\n    return x\n")
    commit(root, "Fix clamp so values stay between lo and hi" + CLAUDE)
    (root / "README.md").write_text("hi\n")
    commit(root, "Add readme" + CLAUDE)
    (root / "calc.py").write_text((root / "calc.py").read_text() + "\n\ndef double(x):\n    return 2 * x\n")
    commit(root, "Add double (by a person)")
    return root


CLAIM_TEST = ("import unittest\nfrom calc import clamp\n\nclass C(unittest.TestCase):\n"
              "    def test_high(self):\n        self.assertEqual(clamp(50, 0, 9), 9)\n")


def fake_worker(holds=False, test=CLAIM_TEST, path=None, name="test_bite_claim.py"):
    def w(cfg, folder, c, diff, budget):
        (folder / name).write_text(test if not holds else test.replace("50", "5").replace("9)", "5)"))
        return {"test_file": path or name,
                "claim": "clamp keeps values in range", "result": "fails", "why": "high end not clamped"}
    return w


def run(root, argv, worker, verdict="REAL"):
    recent.worker = worker
    recent.judge = lambda cfg, c, diff, test, fail: {"verdict": verdict, "matters": 2, "bug": "clamp lets values above hi through"}
    recent.SPENT[0] = 0.0
    cwd = os.getcwd()
    os.chdir(root)
    try:
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = recent.main([a for a in argv if a != "--keep"] if "--keep" in argv else argv + ["--again"])
        return rc, buf.getvalue()
    finally:
        os.chdir(cwd)


# Error guidance must name setup steps that actually exist, without a real key.
with tempfile.TemporaryDirectory() as tmp:
    missing = Path(tmp) / "missing.ini"
    try:
        recent.bite.Config(missing)
    except SystemExit as exc:
        message = str(exc)
        check("missing config points to optional .bite.ini, not an absent setup command",
              "missing.ini" in message and ".bite.ini" in message and "optional" in message
              and "--setup" not in message)
    else:
        check("missing config fails clearly", False)
    with patch.dict(os.environ, {}, clear=True), patch.object(recent.bite, "KEY_FILE", Path(tmp) / "key.txt"):
        try:
            recent.bite.load_key()
        except SystemExit as exc:
            message = str(exc)
            check("missing key explains environment and key.txt options, not an absent setup command",
                  "ANTHROPIC_API_KEY" in message and "key.txt" in message and "--setup" not in message)
        else:
            check("missing key fails clearly", False)


a = {"subject": "Fix tooltip spacing", "body": "", "sha": "x"}
b = {"subject": "Fix export so saved files aren't truncated", "body": "", "sha": "y"}
for c in (a, b):
    c["score"] = (3 if recent.CLAIM.search(c["subject"]) else 0) + (2 if recent.MATTERS.search(c["subject"]) else 0)
check("claims about saving or data rank above cosmetic ones", b["score"] > a["score"])

root = make_repo()
cs = recent.commits(root, 40, False)
check("only Claude-made commits picked", [c["subject"] for c in cs] == ["Add readme", "Fix clamp so values stay between lo and hi"])
check("--all takes every commit", len(recent.commits(root, 40, True)) == 4)

rc, out = run(root, [], fake_worker())
check("false done found", 'FALSE "DONE": commit' in out and "Fix clamp" in out)
check("unguarded change reported", "unguarded" in out)
check("still broken today", "STILL BROKEN" in out)
check("proof written", (root / "bite_proof" / "REPORT.md").is_file() and
      any(p.name.endswith("test_bite_claim.py") for p in (root / "bite_proof").iterdir()))
check("readme commit not tested (no code)", "Add readme" not in out.split("Bite:")[1].split("\n")[1] if "\n" in out else True)

rc, out = run(root, ["--keep"], fake_worker(holds=True))
check("a claim tested before is not paid for again", "earlier run" in out and "$0.00" in out and 'FALSE "DONE"' in out)

rc, out = run(root, [], fake_worker(holds=True))
check("a claim that holds is not reported", "FALSE" not in out and "held up" in out)

rc, out = run(root, [], fake_worker(), verdict="NOT")
check("second check can veto", "FALSE" not in out and "second check disagreed" in out)

rc, out = run(root, [], fake_worker(path="../../etc/test_bite_claim.py"))
check("test file outside the copy is ignored", "no test written" in out and "FALSE" not in out)

rc, out = run(root, [], fake_worker(test="import nothing_here\n"))
check("test that doesn't load is not a finding", "FALSE" not in out and "didn't load" in out)

rc, out = run(root, ["--free"], fake_worker())
check("--free spends nothing and tests no claims", "FALSE" not in out and "$0.00" in out)

rc, out = run(root, ["--serious"], fake_worker())
check("--serious skips claims that aren't about data, money, logins, security or crashes",
      "FALSE" not in out and "testing the claim" not in out and "Nothing serious to check" in out)

# Fixed later: today's code passes the claim test.
(root / "calc.py").write_text("def clamp(x, lo, hi):\n    return max(lo, min(x, hi))\n")
commit(root, "really clamp (by a person)")
rc, out = run(root, [], fake_worker())
check("fixed since is said so", "fixed since" in out)

# A long free pass: each result shows the moment it's known (even with output sent to a file) and is saved, so
# stopping partway keeps it. And bite_proof/ stays out of the user's git.
root = make_repo()
(root / "calc.py").write_text((root / "calc.py").read_text() + "\n\ndef half(x):\n    return x / 2\n")
commit(root, "Fix half so it handles odd numbers" + CLAUDE)


class Out(io.StringIO):
    flushed = ""

    def flush(self):
        self.flushed = self.getvalue()


real_undo, seen = recent.undo_check, []


def stop_on_second(*a):
    seen.append(1)
    if len(seen) == 2:
        raise KeyboardInterrupt
    return real_undo(*a)


recent.undo_check = stop_on_second
buf, cwd = Out(), os.getcwd()
os.chdir(root)
try:
    with contextlib.redirect_stdout(buf):
        recent.main(["--free", "--again"])
except KeyboardInterrupt:
    pass
finally:
    os.chdir(cwd)
    recent.undo_check = real_undo
check("free pass: the first result is shown before the run ends", "unguarded" in buf.flushed)
log = root / "bite_proof" / "recent_log.json"
check("free pass: stopped partway, the first result is saved",
      log.is_file() and any(c.get("undo") for c in recent.json.loads(log.read_text())["free"]))
run(root, ["--free"], fake_worker())
st = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout
check("bite_proof/ doesn't show up in git status", "bite_proof" not in st)

# test_covers: a change the test command can't reach is listed as such, not called "unguarded".
root = make_repo()
(root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m unittest -q\nallowed_programs = {PY}\n"
                                "test_covers = calc.py, test_*\n")
(root / "view.py").write_text("COLOR = 'red'\n")
commit(root, "Fix the panel colour in the view" + CLAUDE)
rc, out = run(root, ["--free"], fake_worker())
check("test_covers: a commit outside the tests' reach is listed, not checked",
      "outside the tests' reach" in out and "the panel colour" not in out and "Fix clamp" in out)

# No commit claims a fix: say so and stop, rather than spend checks on commits that promise nothing.
root = make_repo()
(root / "calc.py").write_text((root / "calc.py").read_text() + "\n\ndef triple(x):\n    return 3 * x\n")
commit(root, "Triple, for the scoreboard" + CLAUDE)
rc, out = run(root, ["--free", "--last", "1"], fake_worker())
check("no fix claims: says so and checks nothing", "No fix claims found in the last 1" in out and "free check" not in out)
rc, out = run(root, ["--free", "--last", "1", "--any"], fake_worker())
check("--any checks them anyway", "free check of 1" in out)

# A change to comments only isn't a code change: nothing to undo, nothing to flag.
root = make_repo()
(root / "calc.py").write_text("# Clamp helpers.\n" + (root / "calc.py").read_text())
(root / "test_more.py").write_text("import unittest\n\nclass M(unittest.TestCase):\n    def test_ok(self):\n        pass\n")
commit(root, "Add more tests, fix the header comment" + CLAUDE)
rc, out = run(root, ["--free", "--last", "1"], fake_worker())
check("a comment-only edit isn't checked as a code change", "TEST GUARDS NOTHING" not in out and "free check" not in out)

# A test that guards nothing: the commit's own new test still passes with its code change taken out.
root = make_repo()
(root / "calc.py").write_text((root / "calc.py").read_text().replace("2 * x", "x + x if x else 0"))
(root / "test_double.py").write_text("import unittest\nfrom calc import double\n\nclass D(unittest.TestCase):\n"
                                     "    def test_zero(self):\n        self.assertEqual(double(0), 0)\n")
commit(root, "Double zero right away, for the scoreboard" + CLAUDE)
(root / "calc.py").write_text((root / "calc.py").read_text() + "\n\ndef sq(x):\n    return x * x\n")
(root / "test_sq.py").write_text("import unittest\nfrom calc import sq\n\nclass S(unittest.TestCase):\n"
                                 "    def test_sq(self):\n        self.assertEqual(sq(3), 9)\n")
commit(root, "Square, for the scoreboard" + CLAUDE)
rc, out = run(root, ["--free", "--last", "2"], fake_worker())
check("fake test: a commit's own test that passes without its code is reported, by name",
      "TEST GUARDS NOTHING" in out and "test_double.py" in out and "No fix claims" in out)
check("fake test: a commit whose test does fail without its code is not", "test_sq.py" not in out)
rep = (root / "bite_proof" / "FREE_REPORT.md").read_text() if (root / "bite_proof" / "FREE_REPORT.md").is_file() else ""
check("fake test: the report gives the commit, the gap, a rerun recipe and a note for their Claude",
      "Double zero right away" in rep and "What's missing" in rep and "git worktree add" in rep
      and "Hand this to your Claude" in rep and "Checked 2 commit(s): 1 have tests that fail" in out)

# A flagged commit that created a file: `git checkout <sha>^ -- <file>` has no such path to restore, so the
# recipe has to delete it instead.
fresh_root = make_repo()
(fresh_root / "fresh.py").write_text("def triple(x):\n    return 3 * x\n")
commit(fresh_root, "Fix the scoreboard triple" + CLAUDE)
run(fresh_root, ["--free", "--last", "1"], fake_worker())
fresh_rep = (fresh_root / "bite_proof" / "FREE_REPORT.md").read_text()
checkout_lines = [ln for ln in fresh_rep.splitlines() if "git checkout" in ln]
check("free report: a file the commit created is deleted, not put in the git checkout line",
      "rm -f fresh.py" in fresh_rep and not any("fresh.py" in ln for ln in checkout_lines))
# A commit that created a module, in a project that's also pip-installed (#28): with the module deleted from Bite's
# copy, Python would import the installed one and the commit's own test would pass. PYTHONPATH stands in for the install.
inst_root = make_repo()
(inst_root / "fresh.py").write_text("def triple(x):\n    return 3 * x\n")
(inst_root / "test_fresh.py").write_text("import unittest\nfrom fresh import triple\n\nclass F(unittest.TestCase):\n"
                                         "    def test_two(self):\n        self.assertEqual(triple(2), 6)\n")
commit(inst_root, "Fix the scoreboard triple" + CLAUDE)
installed = Path(tempfile.mkdtemp())
(installed / "fresh.py").write_text((inst_root / "fresh.py").read_text())
with patch.dict(os.environ, {"PYTHONPATH": str(installed)}):
    rc, out = run(inst_root, ["--free", "--last", "1"], fake_worker())
check("installed copy: a module the commit created isn't loaded from the install instead (#28)",
      "TEST GUARDS NOTHING" not in out and "guarded" in out)
rc, out = run(root, ["--free", "--last", "1"], fake_worker())
check("a run that flags nothing says what it verified", "Checked 1 commit(s): 1 have tests that fail without their change" in out)

# Noise filters for TEST GUARDS NOTHING (from 7 noise flags on two real repos): another OS, a tidy-up, tests
# written for other code, and a gap a later commit closed. Each would otherwise be flagged.
def weak_commit(subject, test_src=None):
    root = make_repo()
    (root / "calc.py").write_text((root / "calc.py").read_text().replace("2 * x", "x + x if x else 0"))
    (root / "test_double.py").write_text(test_src or ("import unittest\nfrom calc import double\n\nclass D(unittest.TestCase):\n"
                                                      "    def test_zero(self):\n        self.assertEqual(double(0), 0)\n"))
    commit(root, subject + CLAUDE)
    return root


other_os = "macOS" if recent.HERE != "mac" else "Windows"
rc, out = run(weak_commit(f"Double zero right away on {other_os}"), ["--free", "--last", "1"], fake_worker())
check("noise: a change built for another OS isn't flagged", "TEST GUARDS NOTHING" not in out and "built for" in out)
rc, out = run(weak_commit("chore(lint): tidy double"), ["--free", "--last", "1"], fake_worker())
check("noise: a tidy-up isn't flagged", "TEST GUARDS NOTHING" not in out and "tidy-up" in out)
rc, out = run(weak_commit("Refactor double into one line"), ["--free", "--last", "1"], fake_worker())
check("noise: a refactor or rename without a \"refactor:\" prefix isn't flagged", "TEST GUARDS NOTHING" not in out and "tidy-up" in out)
root = make_repo()
(root / "calc.py").write_text('"""Small number helpers."""\n\n' + (root / "calc.py").read_text().replace(
    "def double(x):\n", 'def double(x):\n    """Twice x: handles negatives too."""\n'))
commit(root, "Explain how double handles negatives" + CLAUDE)
rc, out = run(root, ["--free", "--last", "1"], fake_worker())
check("noise: a commit that only edits docstrings isn't flagged", "unguarded" not in out and "Nothing to check" in out)
rc, out = run(weak_commit("Double zero right away", "import unittest\n\nclass D(unittest.TestCase):\n"
                          "    def test_text(self):\n        self.assertEqual('a'.upper(), 'A')\n"), ["--free", "--last", "1"], fake_worker())
check("noise: tests that don't name the changed code aren't flagged", "TEST GUARDS NOTHING" not in out and "don't name" in out)
root = weak_commit("Double zero right away")
(root / "test_double_more.py").write_text("import unittest\nfrom calc import double\nimport inspect\n\nclass E(unittest.TestCase):\n"
                                          "    def test_shortcut(self):\n        self.assertIn('if x else 0', inspect.getsource(double))\n")
commit(root, "Pin the zero shortcut (by a person)")
rc, out = run(root, ["--free", "--last", "2"], fake_worker())
check("noise: a gap a later commit closed isn't flagged", "TEST GUARDS NOTHING" not in out and "closed since" in out)
check("noise filters keep real catches: the plain weak test is still flagged",
      "TEST GUARDS NOTHING" in run(weak_commit("Double zero right away"), ["--free", "--last", "1"], fake_worker())[1])

# free_test_command: step 1 uses the faster command, step 2 still uses test_command.
root = make_repo()
(root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m unittest -q\nallowed_programs = {PY}\n"
                                f"free_test_command = {PY} -c \"import sys; sys.exit(3)\"\n")
rc, out = run(root, [], fake_worker())
check("free_test_command: the free pass runs it", "tests fail at this commit" in out)
check("free_test_command: the claim test still runs with the full command", 'FALSE "DONE"' in out)

# When the tests fail on Bite's copy, it says what broke (e.g. a file the project makes only at install time).
root = make_repo()
(root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m unittest -q\nallowed_programs = {PY}\n"
                                f"free_test_command = {PY} -c \"import pkg.version\"\n")
rc, out = run(root, ["--free"], fake_worker())
check("tests that fail on the copy: Bite prints why", "why: ModuleNotFoundError: No module named 'pkg'" in out)

# .NET: Bite finds the test command, and runs one claim test by class name (dotnet test takes no file path).
import bite  # noqa: E402
net = Path(tempfile.mkdtemp())
(net / "src" / "Calc.Tests").mkdir(parents=True)
(net / "src" / "Calc.Tests" / "Calc.Tests.csproj").write_text("<Project/>")
(net / "src" / "Calc").mkdir()
(net / "src" / "Calc" / "Calc.csproj").write_text("<Project/>")
check("dotnet: the one test project is found when there's no solution", bite.guess_test_command(net) == "dotnet test src/Calc.Tests/Calc.Tests.csproj")
(net / "My Game.sln").write_text("")
check("dotnet: a solution is named (quoted when it has a space)", bite.guess_test_command(net) == 'dotnet test "My Game.sln"')
(net / "ProjectSettings").mkdir()
(net / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.1f1\n")
check("Unity: no guess (its tests run inside the editor)", bite.guess_test_command(net) == "")


class GlobCfg:
    test_glob = bite.DEFAULT_TEST_FILES


check("dotnet: C# test files and test projects count as tests",
      bite.is_test_file("sim/Game.Sim.Tests/HeatTests.cs", GlobCfg) and bite.is_test_file("src/Calc.Test/Util.cs", GlobCfg)
      and not bite.is_test_file("sim/Game.Sim/Heat.cs", GlobCfg))


class NetCfg:
    claim_cmd, contain, box_test_cmd = "", "", ""
    test_cmd = 'dotnet test Game.sln --filter "Category!=Slow" -v q'


cmd = recent.claim_command(NetCfg, "tests/Game.Tests/BiteClaimTests.cs")
check("dotnet: claim test picked by --filter, not by file path",
      cmd == 'dotnet test Game.sln -v q --filter "FullyQualifiedName~BiteClaim"')
check("dotnet: a C# build error is a load failure, not a finding",
      bite.load_failure("Calc.cs(3,5): error CS0103: The name 'x' does not exist"))

check("dotnet: a test run that ran no tests isn't a pass",
      recent.ran_nothing("dotnet test tests/App.Tests", "Build succeeded.\n  App.Tests -> bin/App.Tests.dll\n")
      and not recent.ran_nothing("dotnet test x.sln", "Passed!  - Failed: 0, Passed: 112, Skipped: 1, Total: 113"))
root = make_repo()
(root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m unittest -q\nallowed_programs = {PY}\n"
                                f"claim_command = {PY} -c \"print('No test matches the given testcase filter')\"\n")
rc, out = run(root, [], fake_worker())
check("dotnet: a filter that matched no test is not a claim that holds",
      "    test didn't load" in out and "    holds" not in out and "FALSE" not in out)

root = make_repo()  # C# names its files BiteClaimTests.cs, not bite_claim
(root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m unittest -q\nallowed_programs = {PY}\n"
                                f"claim_command = {PY} -m unittest -q {{file}}\n")
rc, out = run(root, [], fake_worker(name="BiteClaimTests.py"))
check("a C#-style name (BiteClaimTests) counts as the claim test file", 'FALSE "DONE"' in out and "no test written" not in out)

# Git LFS: git archive writes pointer files; Bite's copy gets the real content from the repo's LFS store.
import hashlib  # noqa: E402
root = make_repo()
real = b"\x89PNG real art bytes\n" * 50
oid = hashlib.sha256(real).hexdigest()
ptr = f"version https://git-lfs.github.com/spec/v1\noid sha256:{oid}\nsize {len(real)}\n".encode()
(root / "art.png").write_bytes(ptr)
(root / "gone.png").write_bytes(ptr.replace(oid.encode(), b"0" * 64))
(root / ".gitattributes").write_text("*.png -text\n")  # as in LFS repos: no line-ending changes (Windows autocrlf)
commit(root, "add art")
store = root / ".git" / "lfs" / "objects" / oid[:2] / oid[2:4]
store.mkdir(parents=True)
(store / oid).write_bytes(real)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    copy = recent.export(root, recent.repo.git(root, "rev-parse", "HEAD"), recent.repo.load_cfg(root))
check("LFS: a pointer file gets its real content in Bite's copy", (copy / "art.png").read_bytes() == real)
check("LFS: a file that can't be fetched stays a pointer and Bite says so",
      (copy / "gone.png").read_bytes() == ptr.replace(oid.encode(), b"0" * 64) and "Git LFS" in buf.getvalue())

# Options: a typo or --help must never fall through to the paid step.
for args, code in ((["--help"], 0), (["--fre"], 2), (["--budget"], 2), (["--last", "5", "--bogus"], 2)):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = recent.main(args)
    check(f"options: {' '.join(args)} exits {code} before any check runs",
          rc == code and "free check of" not in buf.getvalue())

# First run: a missing test runner is named, with the fix, before any copy is made (not "exit 1" per commit).
root = make_repo()
(root / ".bite.ini").write_text(f"[kit]\ntest_command = {PY} -m pytest -q\nallowed_programs = {PY}\n")
real_run = subprocess.run
no_pytest = lambda a, *k, **kw: (subprocess.CompletedProcess(a, 1) if a[1:] == ["-c", "import pytest"]  # noqa: E731
                                 else real_run(a, *k, **kw))
with patch.object(recent.subprocess, "run", no_pytest):
    rc, out = run(root, ["--free"], fake_worker())
check("first run: pytest missing says so and gives the install line, before any check",
      rc == 1 and "pytest isn't installed" in out and "-m pip install pytest" in out and "free check of" not in out)
(root / ".bite.ini").write_text(f"[kit]\ntest_command = no-such-runner-xyz run\nallowed_programs = {PY}\n")
rc, out = run(root, ["--free"], fake_worker())
check("first run: a test command that isn't installed is named", rc == 1 and "can't find 'no-such-runner-xyz'" in out)
with patch.object(recent.shutil, "which", lambda name: None if name == "git" else "x"):
    rc, out = run(root, ["--free"], fake_worker())
check("first run: no git says how to get it, no traceback", rc == 1 and "git isn't installed" in out)

# Report: every run leaves one page that says what was checked and how each commit did.
root = make_repo()
(root / "calc.py").write_text((root / "calc.py").read_text() + "\n\ndef neg(x):\n    return -x\n")
commit(root, "Fix <b>neg</b> & friends" + CLAUDE)
rc, out = run(root, ["--free"], fake_worker())
page = (root / "bite_proof" / "report.html").read_text(encoding="utf-8") if rc == 0 else ""
check("report: report.html is written and named at the end of a run", "report.html" in out and "<table>" in page)
check("report: a commit nobody's test guards is shown as such", "No test notices if this change is taken out" in page)
note = (root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8") if rc == 0 else ""
check("comment: the pull request comment leads with a plain verdict and what to do",
      note.startswith("<!-- bite-check -->\n### ⚠️ Bite: 2 changes worth a look") and "**What to do:**" in note
      and "<details>" in note and "Fix &lt;b&gt;neg" in note)
check("report: commit subjects are escaped, not run as HTML", "Fix &lt;b&gt;neg&lt;/b&gt; &amp; friends" in page)

# Every kind of comment ends the same way: the fold with the same words on how Bite checks, then the link.
c1 = {"sha": "a" * 40, "subject": "one"}
notes = {"worth a look": note}
for name, cs in (("tests check it", [dict(c1, undo="guarded")]), ("couldn't check", [dict(c1, undo="tests fail at this commit")]),
                 ("no code", [])):
    notes[name] = recent.write_comment(root, cs).read_text(encoding="utf-8")
rc, out = run(root, ["--free", "--last", "0"], fake_worker())
notes["nothing in the pull request"] = (root / "bite_proof" / "COMMENT.md").read_text(encoding="utf-8") if rc == 0 else ""
how = "Bite takes each commit's code change back out and runs your tests. A test that really checks a change fails when the change is gone."
check("comment: every kind (worth a look, tests check it, couldn't check, no code) ends with the same words and link",
      all(n.startswith("<!-- bite-check -->\n### ") and how in n
          and n.endswith("[What is Bite?](https://github.com/connabyss/bite)\n\n</details>\n") for n in notes.values()))
check("comment: a run with nothing to check still writes the comment the GitHub Action posts",
      "No commit in this pull request changed code" in notes["nothing in the pull request"])

# Docs: the key rule is stated where a reader looks first.
for doc in ("AGENTS.md", "README.md"):
    t = (KIT / doc).read_text(encoding="utf-8")
    check(f"{doc}: says Bite needs an API key and never uses a Claude login, with the SDK rule's link",
          "never uses" in t and "login" in t and "https://code.claude.com/docs/en/agent-sdk/overview" in t)
check("CLAUDE.md: loads AGENTS.md, so Claude reads the same instructions as every other coding AI",
      "@AGENTS.md" in (KIT / "CLAUDE.md").read_text(encoding="utf-8"))

check("action.yml: the pull request check runs the free pass and the README shows how to add it",
      "bite --free" in (KIT / "action.yml").read_text(encoding="utf-8")
      and "uses: connabyss/bite@" in (KIT / "README.md").read_text(encoding="utf-8"))

print(f"\n{sum(OK)}/{len(OK)} passed")
sys.exit(0 if all(OK) else 1)

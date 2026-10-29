"""
Bite recent: did your coding agent's recent "done" commits really do what they said?

    python recent.py                 check the last 40 commits made with Claude Code (needs a key for step 2)
    python recent.py --free          step 1 only: no key, no cost
    python recent.py --all           every commit, not only Claude-made ones
    python recent.py --last 80 --suspects 3 --budget 1.00
    python recent.py --serious       only fix claims about data, money, logins, security, crashes or leaks
    python recent.py --any           check commits even when none of them claims a fix
    (installed with pip install -e ., the same runs as: bite, bite --free, ...)

Step 1 (free): for each commit that changed code, the change is taken back out and the tests are run. If they
still pass, no test shows the change does anything ("unguarded"). If the commit added or changed tests and
those still pass without its code change, they test nothing it did ("TEST GUARDS NOTHING"). Commits that
claim a fix come first.
Step 2 (key, capped by --budget): for the top suspects, a fresh worker turns the commit's own claim into one
small test (with the odd inputs the claim covers) on a copy of the project at that commit. Bite then runs the
test itself, twice, at that commit and on today's code, and a second fresh check must agree that the test asks
only for what the commit claimed and fails for a real reason. Only then is it shown as a false "done".

Proof is written to bite_proof/ in the repo: each failing test plus the command that runs it.
Settings: .bite.ini in the repo (optional; first line [kit], then test_command = ...). claim_command runs one
test file ({file}); without it Bite adds the file to test_command (for dotnet test it adds a --filter instead).
test_covers = the paths the test command can reach (globs, comma-separated, e.g. Assets/Sim/*, tests/*): commits
that touch none of them are listed as outside the tests' reach, not checked. free_test_command = a faster subset
of the tests for step 1 (step 2 still uses test_command).
Needs bite.py and repo.py next to it.

Bite needs an API key for step 2 and never uses a Claude login or plan: Anthropic's rules for tools built on the
Agent SDK (https://code.claude.com/docs/en/agent-sdk/overview) say they must use API keys.
"""

import asyncio
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bite  # noqa: E402
import repo  # noqa: E402

CLAUDE_MARK = re.compile(r"Co-Authored-By:\s*Claude|Generated with \[?Claude Code|claude\.ai/code|"
                         r"noreply@anthropic\.com", re.I)
CLAIM = re.compile(r"\b(fix(e[sd])?|handle[sd]?|prevent[sd]?|correct(s|ed)?|resolve[sd]?|guard|avoid[sd]?|"
                   r"support[sd]?|make[sd]? .* work|no longer|now (works|handles|returns|accepts|respects))\b", re.I)
NOT_CODE = re.compile(r"\b(docs?|readme|typo|changelog|bump|release|version|lint|format(ting)?|ci|workflow)\b", re.I)
# Claims about these come first: a miss there loses data or money, locks people out, or crashes.
MATTERS = re.compile(r"\b(sav(e|es|ed|ing)|writ(e|es|ing)|delet\w*|remov\w*|overwrit\w*|data|loss|lost|corrupt\w*|"
                     r"migrat\w*|money|price|pric\w*|payment|billing|invoice|amount|balance|auth\w*|login|password|"
                     r"token|permission\w*|secur\w*|crash\w*|hang\w*|leak\w*|race|deadlock)\b", re.I)
SPENT = [0.0]
# A change built for another OS can't be checked here: its code path never runs, so every test passes without it.
PLATFORM_WORDS = {"win": r"windows|win32|powershell|ntfs|max_path|userprofile|\.ps1\b|cmd\.exe",
                  "mac": r"macos|mac os|darwin|apfs|osx", "linux": r"linux"}
HERE = "win" if sys.platform.startswith("win") else "mac" if sys.platform == "darwin" else "linux"
# Tidy-up commits: nothing in them is meant to change behaviour, so "nothing fails without it" isn't news.
TIDY = re.compile(r"^(chore|style|ci|refactor|build|docs?|tests?)(\([^)]*\))?!?:|\b(lint|tidy|tidies|sort(ed)? imports|"
                  r"reformat\w*|formatting|whitespace|typos?)\b", re.I)
# dotnet test exits 0 when its --filter matches no test: that's a test that never ran, not a claim that holds.
RAN_NOTHING = re.compile(r"No test matches the given testcase filter|No test is available in")
DOTNET_FILTER = '--filter "FullyQualifiedName~BiteClaim"'


def ran_nothing(cmd: str, out: str) -> bool:
    """A run that passed without running any test (dotnet test on a project that isn't a test project, a filter
    that matched nothing) shows nothing about the code."""
    if RAN_NOTHING.search(out):
        return True
    return bool(re.search(r"\bdotnet(\.exe)?\s+test\b", cmd)) and not re.search(r"Total(?: tests)?:\s*[1-9]", out)


LFS_HEAD = b"version https://git-lfs.github.com/spec/v1"
LFS_WARNED = set()


# ---- which commits ---------------------------------------------------------------

def commits(root: Path, last: int, everyone: bool) -> list:
    raw = repo.git(root, "log", f"-n{last}", "--no-merges", "--format=%H%x1f%an%x1f%ae%x1f%s%x1f%b%x1e") or ""
    out = []
    for rec in raw.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        parts += [""] * (5 - len(parts))  # git's output is stripped, so the last body can lose its separator
        if not parts[0]:
            continue
        sha, name, mail, subject, body = parts
        if everyone or CLAUDE_MARK.search(body) or CLAUDE_MARK.search(mail) or "claude" in name.lower():
            out.append({"sha": sha, "subject": subject.strip(), "body": body.strip()})
    return out


def skip_reason(subject: str, said: str) -> str:
    """Why this commit can't say anything here, or "" when it can."""
    text = said.lower()
    built_for = {os_ for os_, words in PLATFORM_WORDS.items() if re.search(rf"\b({words})", text)}
    if "case-insensitive file" in text:
        built_for |= {"win", "mac"}
    if built_for and HERE not in built_for:
        names = {"win": "Windows", "mac": "macOS", "linux": "Linux"}
        return f"built for {'/'.join(sorted(names[o] for o in built_for))}, can't be checked on {names[HERE]}"
    if TIDY.search(subject):
        return "a tidy-up (no behaviour change meant)"
    return ""


def tests_touch(root: Path, c: dict) -> bool:
    """The commit's own tests name the code it changed: a changed file's module or class, or a function or class
    the change defines. Tests that name none of them were written for other code."""
    names = set()
    for rel in c["code"]:
        names.add(Path(rel).stem)
        diff = repo.git(root, "diff", f"{c['sha']}^", c["sha"], "--", rel) or ""
        lines = re.findall(r"(?m)^(?:[-+](?![-+])|@@.*?@@)(.*)$", diff)  # changed lines and hunk headers
        for ln in lines:
            names |= set(re.findall(r"^\s*(?:export\s+|async\s+|pub\s+)*(?:def|class|function|func|fn|struct|interface|enum|record)\s+(\w+)", ln))
            names |= set(re.findall(r"^\s*(?:public|private|internal|protected)\b[\w<>\[\], ?]*?\s(\w+)\s*[({=;]", ln))
    names = {n for n in names if len(n) > 2 and n not in {"__init__", "index", "main", "utils", "util", "test"}}
    for t in c.get("test_code", []):
        src = repo.git(root, "show", f"{c['sha']}:{t}") or ""
        if any(re.search(rf"\b{re.escape(n)}\b", src) for n in names):
            return True
    return not names


def comment_only(root: Path, sha: str, rel: str) -> bool:
    """The change to this file is comments or whitespace only: undoing it can't make a test fail."""
    def code(rev):
        b = repo.git(root, "cat-file", "blob", f"{rev}:{rel}", raw=True)
        if b is None:
            return None
        suf = Path(rel).suffix.lower()
        return [t for t in ("".join(bite.strip_comment(ln, suf).split()) for ln in b.decode("utf-8", "replace").splitlines()) if t]
    old, new = code(f"{sha}^"), code(sha)
    return old is not None and old == new


def files_of(root: Path, c: dict, cfg) -> None:
    names = (repo.git(root, "diff-tree", "--no-commit-id", "-r", "--name-only", "--no-renames", c["sha"]) or "").split("\n")
    names = [n for n in names if n]
    c["tests"] = [n for n in names if bite.is_test_file(n, cfg)]
    c["code"] = [n for n in names if n not in c["tests"] and Path(n).suffix.lower() in repo.CODE_SUFFIXES
                 and not repo.is_setup(n, cfg) and not comment_only(root, c["sha"], n)]
    stat = repo.git(root, "diff", "--shortstat", f"{c['sha']}^", c["sha"], "--", *c["code"]) if c["code"] else ""
    c["lines"] = sum(int(x) for x in re.findall(r"(\d+) (?:insertion|deletion)", stat or ""))
    claims = bool(CLAIM.search(c["subject"])) and not NOT_CODE.search(c["subject"])
    c["claims"] = claims
    # Trailers out first: "Co-Authored-By" would match auth in every Claude commit.
    said = c["subject"] + " " + re.sub(r"(?im)^[\w-]+-by:.*$", "", c["body"])[:400]
    c["serious"] = claims and bool(MATTERS.search(said))
    c["skip"] = skip_reason(c["subject"], said)
    c["test_code"] = [n for n in c["tests"] if Path(n).suffix.lower() in repo.CODE_SUFFIXES]
    # No test is suspect, and so is a new test (it may check nothing the change did): the free pass tells which.
    c["score"] = ((3 if claims else 0) + (2 if not c["tests"] or c["test_code"] else 0) + (1 if 0 < c["lines"] <= 80 else 0)
                  + (2 if MATTERS.search(said) else 0))


def export(root: Path, sha: str, cfg) -> Path:
    """The project as it was at this commit, in a fresh folder (git archive, so nothing of yours is touched)."""
    dest = Path(tempfile.mkdtemp(prefix="bite_recent_")) / root.name
    dest.mkdir()
    data = subprocess.run(["git", "archive", "--format=tar", sha], cwd=root, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=data, capture_output=True)
    lfs_fill(root, dest, data)
    for name in cfg.copy_ignore:  # nothing to do for most repos: ignored files aren't committed
        for p in dest.rglob(name):
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else None
    return dest


def lfs_fill(root: Path, dest: Path, tar: bytes) -> int:
    """git archive writes Git LFS files as small pointer files. Put the real content back, from the repo's own LFS
    store or with git-lfs; warn once about any left as pointers, since a test that reads them fails on the copy.
    Returns how many are still pointers."""
    pointers = []
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        for m in t:
            if m.isfile() and m.size < 1024:
                head = t.extractfile(m).read()
                if head.startswith(LFS_HEAD):
                    pointers.append((m.name, head))
    if not pointers:
        return 0
    store = Path(repo.git(root, "rev-parse", "--path-format=absolute", "--git-common-dir") or root / ".git") / "lfs" / "objects"
    left, smudge = [], True
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    for name, ptr in pointers:
        oid = re.search(rb"oid sha256:([0-9a-f]{64})", ptr)
        obj = store / oid.group(1)[:2].decode() / oid.group(1)[2:4].decode() / oid.group(1).decode() if oid else None
        if obj and obj.is_file():
            bite.safe_write(dest, dest / name, obj.read_bytes())
            continue
        real = b""
        try:  # not downloaded here yet: git-lfs can fetch it, if it's installed (after one failure, stop trying)
            r = subprocess.run(["git", "lfs", "smudge", "--", name], cwd=root, input=ptr, capture_output=True,
                               timeout=120, env=env) if smudge else None
            real = r.stdout if r and r.returncode == 0 else b""
        except (OSError, subprocess.TimeoutExpired):
            pass
        smudge = smudge and bool(real)
        if real and not real.startswith(LFS_HEAD):
            bite.safe_write(dest, dest / name, real)
        else:
            left.append(name)
    if left and str(root) not in LFS_WARNED:
        LFS_WARNED.add(str(root))
        print(f"  note: {len(left)} Git LFS file(s) are only pointer files in Bite's copies (e.g. {left[0]}): install "
              "git-lfs and run `git lfs pull` so tests that read them work there.")
    return len(left)


def at(cfg, folder: Path):
    import copy as _copy
    c = _copy.copy(cfg)
    c.project = folder.resolve()
    return c


# ---- step 1: free ----------------------------------------------------------------

def undo_check(root: Path, c: dict, cfg) -> str:
    """'unguarded' when the tests still pass with this commit's code change taken back out; 'TEST GUARDS NOTHING'
    when that includes the tests the commit itself added or changed (they're kept: only the code is undone)."""
    folder = export(root, c["sha"], cfg)
    fcfg = at(cfg, folder)
    if getattr(cfg, "free_cmd", ""):  # the faster subset, for this step only
        fcfg.test_cmd, fcfg.box_test_cmd = cfg.free_cmd, ""
    try:
        now = bite.run_tests(fcfg, folder)
        if not now["ok"]:
            errs = [ln.strip(" E>") for ln in now["out"].splitlines() if re.search(r"\b\w+(?:Error|Exception)\b:", ln)]
            c["why"] = (errs[-1] if errs else now["why"])[:160]
            return "tests fail at this commit"
        if ran_nothing(bite.tests_cmd(fcfg), now["out"]):
            return "no tests ran at this commit"
        for rel in c["code"]:
            old = repo.git(root, "cat-file", "blob", f"{c['sha']}^:{rel}", raw=True)
            t = folder / rel
            if old is None:
                t.unlink(missing_ok=True)
            else:
                bite.safe_write(folder, t, old)
        undone = bite.run_tests(fcfg, folder)
        if undone["ok"]:  # would be flagged: first rule out the usual harmless reasons
            if c.get("skip"):
                return f"not flagged: {c['skip']}"
            if c.get("test_code") and not tests_touch(root, c):
                return "not flagged: its tests don't name the changed code (likely for other code)"
            if closed_since(root, c, cfg):
                return "closed since: today's tests catch it"
            return "TEST GUARDS NOTHING" if c.get("test_code") else "unguarded"
        return "guarded" if not bite.load_failure(undone["out"]) else "guarded (tests use the new code)"
    finally:
        shutil.rmtree(folder.parent, ignore_errors=True)


def closed_since(root: Path, c: dict, cfg) -> bool:
    """A later commit may have closed the gap: on today's code, take this commit's change back out (if it still
    applies) and see whether today's tests now fail where they passed before."""
    head = repo.git(root, "rev-parse", "HEAD")
    if not head or head == c["sha"]:
        return False
    diff = repo.git(root, "diff", "--binary", f"{c['sha']}^", c["sha"], "--", *c["code"], raw=True)
    folder = export(root, head, cfg)
    fcfg = at(cfg, folder)
    if getattr(cfg, "free_cmd", ""):
        fcfg.test_cmd, fcfg.box_test_cmd = cfg.free_cmd, ""
    try:
        if not diff or subprocess.run(["git", "apply", "-R", "--check", "-"], cwd=folder, input=diff,
                                      capture_output=True).returncode != 0:
            return False  # today's code moved on: can't tell
        now = bite.run_tests(fcfg, folder)
        if not now["ok"] or ran_nothing(bite.tests_cmd(fcfg), now["out"]):
            return False
        subprocess.run(["git", "apply", "-R", "-"], cwd=folder, input=diff, capture_output=True)
        undone = bite.run_tests(fcfg, folder)
        return not undone["ok"] and not bite.load_failure(undone["out"])
    finally:
        shutil.rmtree(folder.parent, ignore_errors=True)


# ---- step 2: the claim, turned into a test ----------------------------------------

WORKER_SYSTEM = """You check one claim a coding agent made in a commit message. You are on a copy of the project
exactly as it was at that commit. Your job: write ONE small test that checks what the commit message says is now
true, and run it.

Rules:
- Test only what the message (and the diff's evident intent) claims. Don't test other features or ask for more.
- Be a skeptic, not a fan: the commit's own tests already cover the happy path. Look for where the claim is
  WIDER than the change: the message says "handles X" but the diff covers one form of X; it says "every" or
  "always" but one branch, caller, file format or platform path was missed; a sibling function with the same
  bug was left alone; the fix works once but not on the second call, a reload, or a round trip. Test those.
- Include the odd inputs the claim plainly covers: empty, None, zero, unicode, duplicates, boundaries.
  Small and readable, under 40 lines.
- Use the project's own test framework and conventions. Put the test in ONE new file whose name contains
  bite_claim and that the project's test runner picks up (for pytest: test_bite_claim.py), next to the
  project's other tests. Don't edit any other file. For .NET (dotnet test): BiteClaimTests.cs with a test
  class named BiteClaimTests, inside the folder of an existing test project so that project compiles it.
- Run it: `pytest <your file>` runs only your test if pytest is the runner; for .NET,
  `dotnet test <the test project> --filter "FullyQualifiedName~BiteClaim"`; `bite-test` runs the whole suite. If it fails, read the failure and make sure the TEST is right (right import, right API, right
  expectation from the claim) before you conclude the code is wrong. A failure from your own mistake is not a finding.
- Finish with one line of JSON and nothing after it:
  {"test_file": "<path relative to the project>", "claim": "<the claim in your words>", "result": "fails" or "holds", "why": "<one sentence>"}"""

JUDGE_PROMPT = """A commit said:
---
{msg}
---
Its diff (code files):
---
{diff}
---
A checker wrote this test of that claim:
---
{test}
---
Run on the code at that commit, the test fails like this:
---
{fail}
---
Answer strictly. Is this a fair test of what the commit claimed (it doesn't ask for more than the claim or the
change's evident intent), and does it fail because the code really doesn't do what was claimed (not because the
test is wrong, uses a wrong API, or expects behaviour nobody promised)?
Then, if REAL, how much it matters: +1 each for: real users would hit it; it loses or corrupts data or money;
it would be embarrassing if a user found it.
Reply with one line of JSON only: {{"verdict": "REAL" or "NOT", "matters": 0-3, "bug": "<the false claim in one plain sentence>",
"why": "<one sentence>"}}"""


def last_json(text: str) -> dict:
    for m in reversed(list(re.finditer(r"\{[^{}]*\}", text or ""))):
        try:
            return json.loads(m.group(0))
        except ValueError:
            continue
    return {}


async def _agent(options, prompt: str):
    from claude_agent_sdk import AssistantMessage, ClaudeSDKClient, ResultMessage, TextBlock
    said, cost = [], 0.0
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                t = [b.text for b in msg.content if isinstance(b, TextBlock) and b.text.strip()]
                if t:
                    said = t
            elif isinstance(msg, ResultMessage):
                cost = msg.total_cost_usd or 0.0
    SPENT[0] += cost
    return "\n".join(said), cost


def worker(cfg, folder: Path, c: dict, diff: str, budget: float) -> dict:
    from claude_agent_sdk import ClaudeAgentOptions
    wcfg = at(cfg, folder)
    opts = ClaudeAgentOptions(cwd=str(folder), model=cfg.model, system_prompt=WORKER_SYSTEM, max_turns=cfg.max_turns,
                              max_budget_usd=budget, allowed_tools=[], disallowed_tools=["WebFetch", "WebSearch", "Task"],
                              can_use_tool=bite.make_permission(wcfg, log=lambda *a: None), permission_mode="default",
                              setting_sources=[], env={"ANTHROPIC_API_KEY": bite.load_key()})
    prompt = f"Commit message:\n{c['subject']}\n\n{c['body']}\n\nThe code change in it:\n{diff}"
    text, _ = asyncio.run(_agent(opts, prompt))
    return last_json(text)


def judge(cfg, c: dict, diff: str, test: str, fail: str) -> dict:
    from claude_agent_sdk import ClaudeAgentOptions

    async def nothing(*a):
        from claude_agent_sdk import PermissionResultDeny
        return PermissionResultDeny(message="No tools: answer from what you were given.")
    opts = ClaudeAgentOptions(model=cfg.judge_model, max_turns=2, max_budget_usd=cfg.judge_budget, allowed_tools=[],
                              can_use_tool=nothing, permission_mode="default", setting_sources=[],
                              env={"ANTHROPIC_API_KEY": bite.load_key()},
                              system_prompt="You check another checker's work. Default to NOT when unsure.")
    msg = f"{c['subject']}\n\n{c['body']}"[:3000]
    text, _ = asyncio.run(_agent(opts, JUDGE_PROMPT.format(msg=msg, diff=diff[:8000], test=test[:4000], fail=fail[:3000])))
    return last_json(text)


def claim_command(cfg, rel: str) -> str:
    """Bite runs the claim test with the project's own test command (never the worker's command line)."""
    if cfg.claim_cmd:
        return cfg.claim_cmd.replace("{file}", rel)
    cmd = bite.tests_cmd(cfg)
    if re.search(r"\bdotnet(\.exe)?\s+test\b", cmd):  # dotnet test takes no file: pick the claim's class by name
        cmd = re.sub(r'\s--filter(\s+|=)("[^"]*"|\S+)', "", cmd)
        return f"{cmd} {DOTNET_FILTER}"
    if "pytest" in cmd:  # keep the runner and its options, drop the folders it was given: only this file runs
        toks = cmd.split()
        i = next(i for i, t in enumerate(toks) if "pytest" in t)
        keep = toks[:i + 1] + [t for t in toks[i + 1:] if t.startswith("-")]
        for opt in ("-p", "-c", "-k", "-m", "--rootdir"):  # options that take a value
            keep += [toks[j + 1] for j in range(i + 1, len(toks) - 1) if toks[j] == opt and toks[j + 1] not in keep]
        return " ".join(keep) + " " + rel
    return f"{cmd} {rel}"


def run_claim(cfg, folder: Path, test_rel: str, test_src: bytes, cmd: str) -> tuple:
    """(exit code, output) of the claim test placed into this copy, run by Bite itself."""
    t = folder / test_rel
    t.parent.mkdir(parents=True, exist_ok=True)
    bite.safe_write(folder, t, test_src)
    return bite.locked_run(at(cfg, folder), cmd, folder)


def try_claim(root: Path, c: dict, cfg, budget: float) -> dict:
    res = {"sha": c["sha"], "subject": c["subject"], "status": "holds"}
    diff = repo.git(root, "diff", f"{c['sha']}^", c["sha"], "--", *c["code"]) or ""
    folder = export(root, c["sha"], cfg)
    try:
        w = worker(cfg, folder, c, diff[:12000], budget)
        rel = (w.get("test_file") or "").strip().replace("\\", "/")
        res["worker"] = w
        tf = bite.inside(folder, str(folder / rel)) if rel else None
        if not tf or not tf.is_file() or "biteclaim" not in re.sub(r"[_\-\s]", "", tf.name.lower()):
            res["status"] = "no test written"
            return res
        rel = tf.relative_to(folder.resolve()).as_posix()
        cmd = claim_command(cfg, rel)
        src = tf.read_bytes()
        res.update(test_file=rel, run=cmd, test=src.decode("utf-8", "replace"))
    finally:
        shutil.rmtree(folder.parent, ignore_errors=True)

    # Bite runs it itself, on clean copies: twice at the commit, then on today's code.
    outs = []
    for _ in range(2):
        f = export(root, c["sha"], cfg)
        try:
            outs.append(run_claim(cfg, f, rel, src, cmd))
        finally:
            shutil.rmtree(f.parent, ignore_errors=True)
    if any(rc in cfg.ok_codes and ran_nothing(cmd, out) for rc, out in outs):
        res["status"] = "test didn't load or timed out"
        return res
    if any(rc in cfg.ok_codes for rc, _ in outs):
        res["status"] = "holds" if all(rc in cfg.ok_codes for rc, _ in outs) else "flaky"
        return res
    if any(rc is None for rc, _ in outs) or bite.load_failure(outs[0][1]):
        res["status"] = "test didn't load or timed out"
        return res
    fail = repo.failure_excerpt(outs[0][1], 25)
    res["fail"] = fail
    v = judge(cfg, c, diff, res["test"], fail)
    res["judge"] = v
    if (v.get("verdict") or "").upper() != "REAL":
        res["status"] = "second check disagreed"
        return res
    head = repo.git(root, "rev-parse", "HEAD")
    f = export(root, head, cfg)
    try:
        rc, out = run_claim(cfg, f, rel, src, cmd)
    finally:
        shutil.rmtree(f.parent, ignore_errors=True)
    res["today"] = ("fixed since" if rc in cfg.ok_codes else "can't tell (test doesn't load on today's code)"
                    if rc is None or bite.load_failure(out) else "STILL BROKEN")
    res["status"] = "FALSE DONE"
    res["matters"] = int(v.get("matters") or 0)
    res["bug"] = v.get("bug") or w.get("why", "")
    return res


# ---- report ----------------------------------------------------------------------

def proof_dir(root: Path) -> Path:
    """bite_proof/ in the repo, kept out of git: it's Bite's output, not the project's."""
    d = root / "bite_proof"
    d.mkdir(exist_ok=True)
    ign = d / ".gitignore"
    if not ign.exists():
        ign.write_text("# Bite's output: not part of the project. Delete this file to commit the proof.\n*\n", encoding="utf-8")
    return d


def save_log(root: Path, tried: list, cs: list) -> None:
    """Written after every check, so a run stopped partway keeps what it found."""
    (proof_dir(root) / "recent_log.json").write_text(json.dumps({"tried": tried, "free": [
        {k: c.get(k) for k in ("sha", "subject", "undo", "score")} for c in cs]}, indent=1), encoding="utf-8")


def gap(c: dict) -> str:
    """What the tests miss, in one plain line."""
    if c.get("undo") == "TEST GUARDS NOTHING":
        return (f"its own tests ({', '.join(c['test_code'])}) still pass with its code change taken out, so they "
                "don't check what it changed.")
    return "no test fails with its code change taken out, so nothing would notice if it broke or was lost."


def write_free(root: Path, cfg, flagged: list) -> Path:
    """The free pass's findings, each with a rerun recipe and a note to hand to the user's own Claude."""
    lines = ["# Bite: changes no test checks", "",
             "Found by taking each commit's code change back out (keeping its tests) and running the tests: they "
             "still passed. Free; no model was used.", ""]
    for i, c in enumerate(flagged, 1):
        sha, files = c["sha"], " ".join(c["code"])
        lines += [f"## {i}. {sha[:8]} {c['subject']}", "", f"- What's missing: {gap(c)[0].upper() + gap(c)[1:]}",
                  f"- Code it changed: {', '.join(c['code'])}", "", "Check it yourself (a throwaway copy; your checkout "
                  "isn't touched):", "", "```", f"git worktree add ../bite_check {sha}", "cd ../bite_check",
                  f"git checkout {sha}^ -- {files}", f"{cfg.test_cmd}", "# the tests pass: nothing caught the change being undone",
                  f"cd {root.as_posix()}", "git worktree remove --force ../bite_check", "```", "", "Hand this to your Claude:", "", "```",
                  f"Commit {sha[:8]} (\"{c['subject']}\") changed {', '.join(c['code'])}. With that change undone, "
                  f"the tests still pass ({'its own tests: ' + ', '.join(c['test_code']) if c.get('test_code') else 'no test covers it'}). "
                  "Write one small test of what this commit changed, next to the existing tests. Show that it fails "
                  f"with the change undone (git checkout {sha[:8]}^ -- {files} in a throwaway worktree) and passes "
                  "with it. Don't change the code.", "```", ""]
    p = proof_dir(root) / "FREE_REPORT.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def write_proof(root: Path, found: list) -> Path:
    d = proof_dir(root)
    lines = ["# Bite: false \"done\" commits", ""]
    for i, r in enumerate(found, 1):
        name = f"{r['sha'][:8]}_{Path(r['test_file']).name}"
        (d / name).write_text(r["test"], encoding="utf-8")
        lines += [f"## {i}. {r['sha'][:8]} {r['subject']}", "", f"- What's wrong: {r['bug']}",
                  f"- Today's code: {r['today']}", f"- Matters: {r['matters']}/3", f"- Test: [{name}]({name})",
                  f"- Run it: copy it to `{r['test_file']}`, then `{r['run']}`", "", "```", r["fail"].strip(), "```", ""]
    (d / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return d


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0
    flags, valued = {"--free", "--all", "--any", "--serious", "--again"}, {"--last", "--free-checks", "--budget", "--suspects"}
    i = 0
    while i < len(argv):  # a typo must not fall through to the paid step
        if argv[i] in valued and i + 1 < len(argv):
            i += 2
        elif argv[i] in flags:
            i += 1
        else:
            print(f"Bite: unknown option {argv[i]!r}. Run bite --help for the options.")
            return 2
    opt = lambda k, d: type(d)(argv[argv.index(k) + 1]) if k in argv else d  # noqa: E731
    root = repo.repo_root(os.getcwd())
    if root is None:
        print("Bite: not inside a git repository.")
        return 1
    try:
        cfg = repo.load_cfg(root)
    except repo.ConfigError as e:
        print(f"Bite: {e}")
        return 1
    cfg.claim_cmd = cfg.free_cmd = ""
    covers = []
    ini = Path(os.environ["BITE_CONFIG"]) if os.environ.get("BITE_CONFIG") else root / ".bite.ini"
    if ini.is_file():
        import configparser
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(ini, encoding="utf-8")
        kit = cp["kit"] if "kit" in cp else {}
        cfg.claim_cmd = kit.get("claim_command", "").strip()
        cfg.free_cmd = kit.get("free_test_command", "").strip()
        covers = [g.strip().replace("\\", "/") for g in kit.get("test_covers", "").split(",") if g.strip()]
    if not cfg.test_cmd:
        print("Bite: no test command found; set test_command in .bite.ini")
        return 1
    if not cfg.programs:  # the worker may run the test runner and the project's language, nothing new
        first = cfg.test_cmd.split()[0]
        cfg.programs = sorted({first, "python", "python3", "pytest", "node", "npx", "go", "cargo", "dotnet"} - {"npx"})
    t0 = time.time()
    cs = [c for c in commits(root, opt("--last", 40), "--all" in argv)]
    for c in cs:
        files_of(root, c, cfg)
    cs = [c for c in cs if c["code"]]
    who = "commits" if "--all" in argv else "commits made with Claude Code"
    print(f"Bite: {len(cs)} {who} changed code in the last {opt('--last', 40)}.", flush=True)
    if not cs:
        print("Nothing to check. Try --all, or a larger --last.")
        return 0
    n_out = 0
    if covers:  # a change the test command can't reach can't fail a test: that says nothing about the change
        import fnmatch
        out = [c for c in cs if not any(fnmatch.fnmatch(f, g) for f in c["code"] for g in covers)]
        cs = [c for c in cs if c not in out]
        n_out = len(out)
        if out:
            print(f"  {len(out)} outside the tests' reach (test_covers), not checked: "
                  + ", ".join(c["sha"][:8] for c in out), flush=True)
        if not cs:
            print("Nothing the tests can reach. Check test_covers in .bite.ini.")
            return 0
    free_only = "--free" in argv
    if not any(c["claims"] for c in cs) and "--any" not in argv:
        cs = [c for c in cs if c["test_code"]]
        print(f"No fix claims found in the last {opt('--last', 40)} commits, so there's nothing to hold them to"
              + (f". Checking the {len(cs)} that added tests: do those tests check the change?" if cs else
                 ". (--any checks them anyway.)"), flush=True)
        if not cs:
            return 0
        free_only = True  # no claim to turn into a test
    if "--serious" in argv:  # only fix claims about data, money, logins, security, crashes or leaks
        cs = [c for c in cs if c.get("serious")]
        print(f"  {len(cs)} of them claim a fix about data, money, logins, security, crashes or leaks.")
        if not cs:
            print("Nothing serious to check. Run without --serious to test the other claims.")
            return 0
    cs.sort(key=lambda c: -c["score"])
    logf = root / "bite_proof" / "recent_log.json"
    try:  # read before the free pass saves over it
        kept = json.loads(logf.read_text(encoding="utf-8")).get("tried", [])
    except (OSError, ValueError):
        kept = []
    free = cs[:opt("--free-checks", 6)]
    print(f"  free check of {len(free)}: each runs the tests twice (with and without the change)", flush=True)
    for c in free:
        c["undo"] = undo_check(root, c, cfg)
        if c["undo"].startswith("unguarded"):
            c["score"] += 2
        elif c["undo"] == "TEST GUARDS NOTHING":
            c["score"] += 3
        print(f"  {c['sha'][:8]} {c['undo']:<26} {c['subject'][:70]}", flush=True)
        if c.get("why"):  # say what broke, so it's clear whether it's the project or the copy
            print(f"           why: {c['why']}", flush=True)
        save_log(root, kept, cs)
    cs.sort(key=lambda c: -c["score"])
    found, tried = [], []
    before = [] if "--again" in argv else kept  # claims tested on an earlier run aren't paid for again
    done = {r["sha"] for r in before}
    found = [r for r in before if r.get("status") == "FALSE DONE"]
    cs = [c for c in cs if c["sha"] not in done]
    if before:
        print(f"  {len(done)} claims were tested on an earlier run ({len(found)} false); testing the next ones")
    if not free_only:
        budget = opt("--budget", 1.0)
        n = opt("--suspects", 3)
        for c in cs[:n]:
            left = budget - SPENT[0]
            if left < 0.15:
                print("  budget used up")
                break
            print(f"  testing the claim of {c['sha'][:8]} ...", flush=True)
            r = try_claim(root, c, cfg, min(left - 0.05, budget / n + 0.10))
            tried.append(r)
            print(f"    {r['status']}" + (f": {r.get('today')}" if r["status"] == "FALSE DONE" else ""), flush=True)
            save_log(root, before + tried, cs)
            if r["status"] == "FALSE DONE":
                found.append(r)
    found.sort(key=lambda r: (r["today"] != "STILL BROKEN", -r["matters"]))
    print()
    if found:
        top = found[0]
        print(f"FALSE \"DONE\": commit {top['sha'][:8]} said \"{top['subject']}\".")
        print(f"  {top['bug']}")
        print(f"  Today's code: {top['today']}.")
        print("  The test that shows it:\n" + "\n".join("    " + ln for ln in top["fail"].strip().splitlines()[:10]))
        d = write_proof(root, found)
        tried = before + tried
        print(f"\n{len(found)} false \"done\" in {len(tried)} claims tested. Proof and run commands: {d / 'REPORT.md'}")
    elif tried or before:
        tried = before + tried
        print(f"All {len(tried)} claims tested held up: " + "; ".join(f"{r['sha'][:8]} {r['status']}" for r in tried))
    flagged = [c for c in cs if c.get("undo") == "TEST GUARDS NOTHING" or c.get("undo", "").startswith("unguarded")]
    for c in flagged:
        print(f"{c['undo'].upper()}: {c['sha'][:8]} \"{c['subject'][:70]}\": {gap(c)}")
    checked = [c for c in cs if c.get("undo")]
    held = [c for c in checked if c["undo"].startswith(("guarded", "closed since"))]
    print(f"\nChecked {len(checked)} commit(s): {len(held)} have tests that fail without their change (guarded), "
          f"{len(flagged)} flagged, {len(checked) - len(held) - len(flagged)} couldn't be checked"
          + (f"; {n_out} outside the tests' reach" if n_out else "") + ".")
    if flagged:
        print(f"Each flagged commit, with a check you can rerun and a note for your Claude: {write_free(root, cfg, flagged)}")
    print(f"\n{time.time() - t0:.0f}s, ${SPENT[0]:.2f}")
    save_log(root, tried, cs)
    return 0


if __name__ == "__main__":
    sys.exit(main())

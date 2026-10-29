# recent.py on public repos: does Claude's "fixed" hold up? (2026-10-26/27)

## Headline (round 2): a memory leak Claude said it fixed, still there today
fellowapp/prosemirror-py, commit `3614c96` (Co-Authored-By: Claude): "fix: add weakref callback to clean up resolve
cache entries ... removes the cache entry when the doc is garbage collected." It doesn't. The global cache keeps a
strong reference to each doc through the cached positions, so the doc never dies and the callback never fires.
Bite's 10-line test fails on that commit and on today's code. A standalone check on today's code (repro_leak.py):
after 20,000 documents are resolved and dropped, the cache still holds 20,000 entries and 35 MB.
Proof: recent_prosemirror/ (the test, the failure, the repro). Rated 2 of 3 on "matters" (long-running servers hit it,
and the commit says it's fixed).

## Round 3 (`--serious` only: claims about data, money, logins, security, crashes or leaks; $3.81)

| repo | serious claims tested | false "done" shown | cost |
|---|---|---|---|
| pyrad/pyrad | 15 | 0 (1 vetoed) | $2.04 |
| mercadopago/sdk-python | 1 | 0 | $0.10 |
| fellowapp/prosemirror-py | 6 new | 0 new (the leak above shown again) | $0.85 |
| mnot/http-sf | 1 new | 0 | $0.11 |
| keboola/python-vcr-tests | 5 | **1 (still broken)** | $0.71 |
| **total** | **28 new** | **1** | **$3.81** |

New catch: keboola/python-vcr-tests `3b66c30c` (Co-Authored-By: Claude), "add DB VCR support ... Recording proxy
... captures execute/fetch/description". When one cursor runs several queries, only the last is recorded; the rest
are silently dropped from the cassette, so replay can't find them. Checked by hand on today's code: 3 queries run,
1 recorded. Reported as keboola/python-vcr-tests#18, fix in #19. Proof: recent_vcr/.

## Round 2 (fixed rule picked lightly reviewed, Claude-heavy repos; bite_recent/pick_recent2.py)
3,000 PyPI packages scanned; kept when at least 33 of the last 100 commits are Claude-made, at most 3 human authors,
most Claude commits pushed without a PR number, 5+ Claude fix claims, and a tests folder. 7 kept, the first 5 that
ran in the box were tested, 10 claims each, claims about data, money, logins and crashes first.

| repo | claims tested | false "done" shown | vetoed by the second check | cost |
|---|---|---|---|---|
| fellowapp/prosemirror-py | 10 | **1 (still broken)** | 2 | $1.15 |
| mnot/http-sf | 10 | 0 | 0 | $0.92 |
| keboola/python-vcr-tests | 10 | 0 | 2 | $0.94 |
| bernhard-42/bd_materials | 10 | 0 | 0 | $1.14 |
| datalayer/code-sandboxes | 10 | 0 | 1 | $1.25 |
| **total** | **50** | **1** | **5** | **$5.40** |
(4 of the 50 had no test written; they count as not shown.)

## Round 1

Repos picked by a fixed rule (bite_recent/pick_recent.py): pure-Python PyPI projects whose last 300 commits hold
3+ Claude-made commits that claim a fix. 20 picked; 4 ran their tests in a Docker box by the setup rule.
groundx-python failed that rule (a missing package) and was set up by hand from its requirements.txt, chosen
because it had many Claude commits, before any of its results were seen; otherwise nothing was hand-picked. One run each, Sonnet worker and second check.

| repo | claims tested | false "done" shown | vetoed by the second check | cost |
|---|---|---|---|---|
| eyelevelai/groundx-python | 10 | **2** | 2 | $1.27 |
| anthropics/claude-code-sdk-python | 10 | 0 | 3 | $1.18 |
| wuwentao/midea-lan | 3 | 0 | 0 | $0.49 |
| microsoft/opentelemetry-distro-python | 3 | 0 (2 couldn't run: a missing optional package) | 0 | $0.50 |
| **total** | **26** | **2** | **5** | **$3.44** |

## The two it showed, and how we know they're real
Both are in one pull request (groundx-python #101, GX-33), where Claude committed one claimed fix after another:
- `307c237` "derive Redis db from broker URL path, **guarded**": the guard used `str.isdigit()`, which accepts `'²'`,
  and then `int('²')` crashes. Bite's test: `redis://h:6379/²` raises ValueError. The PR's later commit `d5353dd`
  ("use isdecimal for db guard") fixed exactly this.
- `9cd0853` "guard db conversion with try/except", with the message claiming Status never crashes on any broker
  string: `host:²` still crashes at an unguarded `int()` on another branch. The PR's next commit `b740ab8`
  ("guard legacy-branch port int(); complete broker-parse crash-safety") fixed exactly this.
So twice Claude said "done", Bite's 20-line test failed, and the project's own next commit agreed.
Proof files: recent_groundx/ (the tests and the failure output).

## What this does NOT show (read before quoting it)
- Across all three rounds: 104 claims in 11 repos, 4 false "done" shown, all 4 real; 8 of 11 repos had none.
- Both catches are the same class (Unicode digits), and they matter little: rated 1 of 3 (exotic input).
- 1 repo of 4 had a false "done". On well-reviewed repos (the Claude Agent SDK, midea-lan) every claim held.
- The second check vetoed 5 failing tests; on reading them, each veto was right (a test asked for more than the
  claim, a missing tool, or a branch the commit never touched). No false "done" shown was wrong, but 2 is a small number.
- 4 repos, 26 claims. Raw logs: bite_recent/ in the project that built this (log_*.json, *.out).

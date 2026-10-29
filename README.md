# Bite

**Bite checks whether an AI coding agent's "fixed" is actually true.**

When a commit says it fixed something, Bite writes one small test of that exact claim, runs it itself on the commit and on today's code, and shows the result only if a second, independent check agrees the test is fair. If the test fails, the "fixed" wasn't.

## Try it in a minute

```
git clone https://github.com/connabyss/bite && cd bite
pip install -e .
cd /path/to/your-repo && bite --free
```

`bite --free` needs no key and costs nothing. It takes each recent change back out, runs your tests, and lists
the changes no test guards, plus any new test that still passes without its commit's code (it tests nothing).

To test the claims themselves, `pip install -e .[paid]` and set `ANTHROPIC_API_KEY`, then run `bite`. Each claim
costs about $0.13, and `--budget` caps the total ($1 by default). Bite needs an API key for this step and
never uses a Claude login or plan (Anthropic's Agent SDK rule: https://code.claude.com/docs/en/agent-sdk/overview).

Works with pytest, npm test, cargo test, go test and dotnet test. Settings and limits: [CLAUDE.md](CLAUDE.md),
written so your own Claude can set Bite up for you. Bite's own tests: `pip install -e .[test]` then `python -m pytest`.

## The catch that shows what it's for

In [fellowapp/prosemirror-py](https://github.com/fellowapp/prosemirror-py), commit `3614c96` (co-authored by Claude) says:

> fix: add weakref callback to clean up resolve cache entries
>
> The cache used dict keyed by id(doc) with no cleanup, causing a slow memory leak in long-running processes. Added a weakref finalizer callback that removes the cache entry when the doc is garbage collected.

Bite wrote this test of that claim and ran it:

```python
def test_cache_entry_removed_after_doc_gc():
    resolvedpos._resolve_cache.clear()
    d = doc(p("hello"))
    ResolvedPos.resolve_cached(d, 2)
    assert len(resolvedpos._resolve_cache) == 1
    del d
    gc.collect()
    assert len(resolvedpos._resolve_cache) == 0   # fails: 1 == 0
```

It fails on that commit and on today's code. The cache keeps each document alive through its cached positions, so the cleanup never runs. After 20,000 documents are resolved and dropped, the cache still holds all 20,000, using 35 MB. The commit looked right, read right, and passed its own tests. Reported with a repro in [#335](https://github.com/fellowapp/prosemirror-py/issues/335); a tested fix is open as [#336](https://github.com/fellowapp/prosemirror-py/pull/336).

## Fixed or merged upstream

Each bug was reproduced with a standalone script in a clean environment before it was reported.

| Project | What happened |
|---|---|
| pyclibrary | 7 bugs reported in [#92](https://github.com/MatthieuDartiailh/pyclibrary/issues/92). All 7 fixes reviewed and merged: [#93](https://github.com/MatthieuDartiailh/pyclibrary/pull/93), [#94](https://github.com/MatthieuDartiailh/pyclibrary/pull/94), [#95](https://github.com/MatthieuDartiailh/pyclibrary/pull/95), [#96](https://github.com/MatthieuDartiailh/pyclibrary/pull/96), [#97](https://github.com/MatthieuDartiailh/pyclibrary/pull/97), [#98](https://github.com/MatthieuDartiailh/pyclibrary/pull/98), [#99](https://github.com/MatthieuDartiailh/pyclibrary/pull/99). The maintainer [wrote](https://github.com/MatthieuDartiailh/pyclibrary/issues/92): "Thanks for the small and focused PR very nice to review." |
| django-tailwind-cli | With one stylesheet, `tailwind watch` hid rebuild messages and build errors. Fix [#232](https://github.com/django-commons/django-tailwind-cli/pull/232) merged and released in [4.8.2](https://github.com/django-commons/django-tailwind-cli/releases/tag/v4.8.2). The maintainer [wrote](https://github.com/django-commons/django-tailwind-cli/pull/232): "Just about to release 4.8.2 with the fix included. Thanks for the contribution." |
| srptools | 4 bugs reported in [#13](https://github.com/idlesign/srptools/issues/13). The maintainer fixed all 4 and closed it the same day. |
| resolve-robotics-uri-py | URI lookup depended on the hash seed ([#26](https://github.com/gbionics/resolve-robotics-uri-py/issues/26)). Fixed by the maintainers in [#27](https://github.com/gbionics/resolve-robotics-uri-py/pull/27). The maintainer [wrote](https://github.com/gbionics/resolve-robotics-uri-py/issues/26): "Thanks a lot for the detailed issue report!" |
| text-to-cad | A Claude commit added a Python 3.11 syntax check that can't catch the exact bug it was written for (nested same-quote f-strings). Bite sent a test that does catch it, [#708](https://github.com/earthtojake/text-to-cad/pull/708), was merged and released in [0.8.2](https://github.com/earthtojake/text-to-cad/releases/tag/v0.8.2); the maintainer then closed the remaining gaps in [#712](https://github.com/earthtojake/text-to-cad/pull/712). |

## Sent, waiting for review

| Project | Link | What happened |
|---|---|---|
| prosemirror-py | [#335](https://github.com/fellowapp/prosemirror-py/issues/335), [#336](https://github.com/fellowapp/prosemirror-py/pull/336), [#337](https://github.com/fellowapp/prosemirror-py/pull/337) | The leak above. A second Claude commit (`1e3339e`) let `Mapping` change a list the caller still owned; fix in #337. |
| python-vcr-tests | [#18](https://github.com/keboola/python-vcr-tests/issues/18), [#19](https://github.com/keboola/python-vcr-tests/pull/19) | A Claude commit said its database recorder captures every query; only the last per cursor is saved. |
| ChatSBOM | [#217](https://github.com/WangYihang/ChatSBOM/issues/217) | A Claude commit's stale-result guard is reset on every walk page, so a repo can be collected twice. |
| llm | [#1828](https://github.com/simonw/llm/pull/1828) | A Claude commit fixed per-turn tool ids in `llm logs`, but its test never made a tool call, so it passed even with the bug. |
| treg | [#1237](https://github.com/superdesigndev/treg/pull/1237) | A Claude commit's test for an org header passes even with the fix removed, so it guards nothing. |
| claude-seo | [#392](https://github.com/AgriciDaniel/claude-seo/pull/392) | A Claude commit's `--release` check let a value with a trailing newline through. |
| marshmallow-fastoneofschema | [#1](https://github.com/Kalepa/marshmallow-fastoneofschema/issues/1), [#2](https://github.com/Kalepa/marshmallow-fastoneofschema/pull/2), [#3](https://github.com/Kalepa/marshmallow-fastoneofschema/pull/3), [#4](https://github.com/Kalepa/marshmallow-fastoneofschema/pull/4) | 3 bugs, one fix each. |
| mizani | [#90](https://github.com/has2k1/mizani/pull/90) | Number labels picked too few decimals when values were close together (`[0, 10, 10.5]` showed as `10, 10`). |
| django-modeltranslation | [#831](https://github.com/deschler/django-modeltranslation/pull/831) | Nested `auto_populate()` and `fallbacks()` blocks reset the setting to nothing on exit instead of restoring it. |
| west | [#1013](https://github.com/zephyrproject-rtos/west/pull/1013) | Loading a manifest from data with a reserved project name crashed. |
| midea-lan | [#251](https://github.com/wuwentao/midea-lan/pull/251) | A message encoder got the frame length wrong when no padding was needed. |
| mypy_boto3_builder | [#395](https://github.com/youtype/mypy_boto3_builder/issues/395) | Reported, no reply yet. |
| drf-pydantic | [#51](https://github.com/georgebv/drf-pydantic/issues/51) | Reported, no reply yet. |

## Limits, plainly

- **Most claims hold.** Across all rounds so far, Bite tested 137 "fixed" claims from Claude-made commits that it could run tests for. 8 were false (about 1 in 17), and 4 of those were still broken on today's code. On well-reviewed projects it usually finds nothing, and that's the right answer.
- **Quiet is not a pass.** Bite only shows a failing test that the second check calls fair and real. That second check has thrown out more than 10 failing tests that weren't. A claim that holds proves that one claim, not that the commit has no other bugs.
- **It needs the project's tests to run.** If they don't run on a clean copy, Bite can't check that commit.
- **Bug hunting is weaker than claim checking.** In a 10-project overnight hunt, two blind AI judges rated 21 of 22 proven fixes as real bugs and none as wrong, but Bite found only 1 of the 10 bugs the maintainers fixed soon after.
- **Small samples, AI judges.** The judges read code without running it. The human checks are the maintainers' fixes and merges listed above.

## Contributing

Bug reports, fixes and AI-assisted PRs are all welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). If Bite flagged
something wrongly, or missed a claim you know was false, please [open an issue](../../issues/new/choose).

MIT licensed.

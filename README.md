# Bite

**A proof of concept for an AI referee tool: it checks whether what a coding agent says is done is actually true.**

Bite turns an agent's "fixed" claim into a small test, runs the test itself, and shows a result only when a second, independent check agrees that the test is fair. It also hunts and fixes bugs in a throwaway copy of a project, and calls a fix "proven" only when a test fails without it and passes with it.

The code isn't public yet. This page shows what it has found so far.

## A real example: a fix that wasn't

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

It fails on that commit and on today's code. The cache keeps each document alive through its cached positions, so the cleanup callback never runs. A standalone check on today's code found that after 20,000 documents are resolved and dropped, the cache still holds all 20,000, using 35 MB. Reported upstream with a repro ([prosemirror-py #335](https://github.com/fellowapp/prosemirror-py/issues/335)), and a tested fix is open as [#336](https://github.com/fellowapp/prosemirror-py/pull/336).

## Bugs it found in real open-source projects

Each one was reproduced with a standalone script in a clean environment before it was reported.

| Project | Report | What happened |
|---|---|---|
| prosemirror-py | [#335](https://github.com/fellowapp/prosemirror-py/issues/335) | The memory leak above. Fix sent as [#336](https://github.com/fellowapp/prosemirror-py/pull/336), waiting for review. A second Claude commit (`1e3339e`) let `Mapping` change a list the caller still owned; fix sent as [#337](https://github.com/fellowapp/prosemirror-py/pull/337), waiting for review. |
| srptools | [#13](https://github.com/idlesign/srptools/issues/13) | 4 bugs. The maintainer fixed all 4 and closed it the same day. |
| pyclibrary | [#92](https://github.com/MatthieuDartiailh/pyclibrary/issues/92) | 7 bugs. The maintainer offered to review a PR for each one. All 7 are reviewed and merged: [#93](https://github.com/MatthieuDartiailh/pyclibrary/pull/93), [#94](https://github.com/MatthieuDartiailh/pyclibrary/pull/94), [#95](https://github.com/MatthieuDartiailh/pyclibrary/pull/95), [#96](https://github.com/MatthieuDartiailh/pyclibrary/pull/96), [#97](https://github.com/MatthieuDartiailh/pyclibrary/pull/97), [#98](https://github.com/MatthieuDartiailh/pyclibrary/pull/98), [#99](https://github.com/MatthieuDartiailh/pyclibrary/pull/99). |
| resolve-robotics-uri-py | [#26](https://github.com/gbionics/resolve-robotics-uri-py/issues/26) | URI lookup depended on the hash seed. The maintainers fixed it in [#27](https://github.com/gbionics/resolve-robotics-uri-py/pull/27) and thanked the reporter. |
| django-tailwind-cli | [PR #232](https://github.com/django-commons/django-tailwind-cli/pull/232) | With one stylesheet, `tailwind watch` hid rebuild messages and build errors. Fix merged by the maintainer and released in 4.8.2. |
| mypy_boto3_builder | [#395](https://github.com/youtype/mypy_boto3_builder/issues/395) | Reported, waiting for a reply. |
| drf-pydantic | [#51](https://github.com/georgebv/drf-pydantic/issues/51) | Reported, waiting for a reply. |
| python-vcr-tests | [#18](https://github.com/keboola/python-vcr-tests/issues/18) | A Claude commit said its database recorder captures every query; only the last per cursor is saved. Fix sent as [#19](https://github.com/keboola/python-vcr-tests/pull/19), waiting for review. |
| marshmallow-fastoneofschema | [#1](https://github.com/Kalepa/marshmallow-fastoneofschema/issues/1) | 3 bugs. Fixes sent as [#2](https://github.com/Kalepa/marshmallow-fastoneofschema/pull/2), [#3](https://github.com/Kalepa/marshmallow-fastoneofschema/pull/3) and [#4](https://github.com/Kalepa/marshmallow-fastoneofschema/pull/4), waiting for review. |
| treg | [PR #1237](https://github.com/superdesigndev/treg/pull/1237) | A Claude commit's test for an org header passes even with the fix removed, so it guards nothing. Sent a test that does, waiting for review. |
| text-to-cad | [PR #708](https://github.com/earthtojake/text-to-cad/pull/708) | A Claude commit added a Python 3.11 syntax check that can't catch the exact bug it was written for (nested same-quote f-strings). Sent a test that does. Merged by the maintainer, who then closed the remaining gaps in [#712](https://github.com/earthtojake/text-to-cad/pull/712), also merged. |
| llm | [PR #1828](https://github.com/simonw/llm/pull/1828) | A Claude commit fixed per-turn tool ids in `llm logs`, but its test never made a tool call, so it passed even with the bug. Sent a test that fails on the old code, waiting for review. |
| claude-seo | [PR #392](https://github.com/AgriciDaniel/claude-seo/pull/392) | A Claude commit's `--release` check let a value with a trailing newline through. Fix sent, waiting for review. |
| mizani | [PR #90](https://github.com/has2k1/mizani/pull/90) | Number labels picked too few decimals when values were close together (`[0, 10, 10.5]` showed as `10, 10`). Fix sent, waiting for review. |
| django-modeltranslation | [PR #831](https://github.com/deschler/django-modeltranslation/pull/831) | Nested `auto_populate()` and `fallbacks()` blocks reset the setting to nothing on exit instead of restoring it. Fix sent, waiting for review. |
| west | [PR #1013](https://github.com/zephyrproject-rtos/west/pull/1013) | Loading a manifest from data with a reserved project name crashed. Fix sent, waiting for review. |
| midea-lan | [PR #251](https://github.com/wuwentao/midea-lan/pull/251) | A message encoder got the frame length wrong when no padding was needed. Fix sent, waiting for review. |

## Limitations (honest numbers)

**Checking "fixed" claims.** Bite tested 76 claims from Claude-made commits in 9 open-source projects, all picked by a fixed rule. It showed 3 false "done" claims, and all 3 were real. One is the leak above. The other two were minor, and the projects' own next commits fixed exactly those bugs. 7 of the 9 projects had none: on well-reviewed code, the agents' claims mostly held. The second check threw out 10 failing tests that weren't fair. Later rounds checked about 70 more claims and found 3 more false "done": the python-vcr-tests recorder above and 2 minor ones.

**Hunting bugs overnight.** 10 projects, one night each, with two AI judges reading the claims blind:
- **Proven fixes: 21 of 22 were real bugs**, according to both judges. Neither judge rated any fix as wrong. The judges agreed on 93% of claims.
- **Weak spot:** each project had a bug its maintainers fixed soon after. Bite found only **1 of those 10**.

These are small samples. The judges are AI models that read the code without running it. The only human checks so far are the maintainers' fixes and merges above: 4 bugs fixed in srptools, 7 PRs merged in pyclibrary, 1 in django-tailwind-cli, 1 in text-to-cad (plus the maintainer's own follow-up), and the resolve-robotics-uri-py fix.

## Early access

Want to try Bite on your own project? [Open an issue](../../issues/new) and say a little about the project.

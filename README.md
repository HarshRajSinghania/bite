# Bite

**A referee for AI coding agents.** Bite lets an agent hunt and fix bugs in a throwaway copy of your project, and only calls a fix "proven" when a test fails without the fix and passes with it. Everything else lands in a morning report for a person to look at.

The code isn't public yet. This page shows what it has found so far.

## Bugs it found in real open-source projects

Each one was reproduced with a standalone script in a clean environment before it was reported.

| Project | Report | What happened |
|---|---|---|
| srptools | [#13](https://github.com/idlesign/srptools/issues/13) | 4 bugs. The maintainer fixed all 4 and closed it the same day. |
| pyclibrary | [#92](https://github.com/MatthieuDartiailh/pyclibrary/issues/92) | 7 bugs. The maintainer offered to review a PR for each one. First PR: [#93](https://github.com/MatthieuDartiailh/pyclibrary/pull/93). |
| resolve-robotics-uri-py | [#26](https://github.com/ami-iit/resolve-robotics-uri-py/issues/26) | Reported, waiting for a reply. |
| mypy_boto3_builder | [#395](https://github.com/youtype/mypy_boto3_builder/issues/395) | Reported, waiting for a reply. |
| drf-pydantic | [#51](https://github.com/georgebv/drf-pydantic/issues/51) | Reported, waiting for a reply. |

## How good is it? (honest numbers)

Test: 10 open-source projects, each picked by a fixed rule, one night of Bite each. Two separate AI judges then read Bite's claims without knowing which section of the report each claim came from.

- **Proven fixes: 21 of 22 were real bugs**, according to both judges. Neither judge rated any fix as wrong.
- The judges agreed with each other on 93% of claims.
- **Weak spot:** each project had a bug its maintainers fixed soon after. Bite found only **1 of those 10**. It is good at finding real bugs, but not yet the specific ones maintainers hit next.

Limits: 10 projects is small, the judges read code but did not run it, and the judges are AI models too. A human spot-check would make this stronger.

## Early access

Want to try Bite on your own project? [Open an issue](../../issues/new) and say a little about the project.


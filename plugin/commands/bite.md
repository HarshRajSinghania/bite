---
description: Check the changes since the last commit with Bite (take them out, run the tests)
allowed-tools: Bash(bite live:*)
---

Bite's result for the changes since the last commit:

!`bite live 2>&1 || true`

Tell the user the result above in one or two plain sentences. If it says no test noticed the change, or that
the new tests don't notice it, offer to write a test that fails without the change and passes with it. If the
`bite` command wasn't found, tell the user to install it with `pipx install bite-check` and run /bite again.

# Bite: false "done" commits

## 1. 3614c96c fix: add weakref callback to clean up resolve cache entries

- What's wrong: The commit claims the cache entry is removed when the doc is garbage collected, but the entry is never removed, so the leak is still there.
- Today's code: STILL BROKEN
- Matters: 2/3
- Test: [3614c96c_test_bite_claim.py](3614c96c_test_bite_claim.py)
- Run it: copy it to `tests/prosemirror_model/test_bite_claim.py`, then `python -m pytest -q -p no:cacheprovider tests/prosemirror_model/test_bite_claim.py`

```
=================================== FAILURES ===================================
____________________ test_cache_entry_removed_after_doc_gc _____________________
        assert len(resolvedpos._resolve_cache) == 1
        del d
>       assert len(resolvedpos._resolve_cache) == 0
E       assert 1 == 0
E        +  where 1 = len({140544867460272: <prosemirror.model.resolvedpos._ResolveCache object at 0x7fd326e672f0>})
tests/prosemirror_model/test_bite_claim.py:18: AssertionError
=========================== short test summary info ============================
FAILED tests/prosemirror_model/test_bite_claim.py::test_cache_entry_removed_after_doc_gc
1 failed in 0.12s
```

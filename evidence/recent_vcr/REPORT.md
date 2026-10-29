# Bite: false "done" commits

## 1. 3b66c30c feat: add DB VCR support for recording/replaying database interactions

- What's wrong: The recording proxy captures every execute/fetch on a cursor, but when one cursor runs several statements only the last is recorded and the earlier ones are silently dropped.
- Today's code: STILL BROKEN
- Matters: 2/3
- Test: [3b66c30c_test_bite_claim.py](3b66c30c_test_bite_claim.py)
- Run it: copy it to `tests/test_bite_claim.py`, then `python -m pytest -q -p no:cacheprovider tests/test_bite_claim.py`

```
=================================== FAILURES ===================================
________________ test_two_executes_on_one_cursor_both_recorded _________________
>       assert len(log) == 2
E       AssertionError: assert 1 == 2
E        +  where 1 = len([{'sql_normalized': 'SELECT 2 FROM DUAL', 'params_hash': '37a6259cc0c1dae299a7866489dff0bd', 'description': [['A', 'NUMBER']], 'rows': [[2]]}])
tests/test_bite_claim.py:28: AssertionError
=========================== short test summary info ============================
FAILED tests/test_bite_claim.py::test_two_executes_on_one_cursor_both_recorded
============================== 1 failed in 0.14s ===============================
```

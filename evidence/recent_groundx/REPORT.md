# Bite: false "done" commits

## 1. 9cd08532 fix(extract): guard db conversion with try/except; reconcile GX-33 record

- What's wrong: The commit claims Status.__init__ never crashes on any broker string, but the bare 'host:²' form (no scheme) still raises an uncaught ValueError from int().
- Today's code: fixed since
- Matters: 1/3
- Test: [9cd08532_test_bite_claim.py](9cd08532_test_bite_claim.py)
- Run it: copy it to `tests/extract/services/test_bite_claim.py`, then `python -m pytest -q -p no:cacheprovider tests/extract/services/test_bite_claim.py`

```
=================================== FAILURES ===================================
_____________________ test_status_never_crashes[host:\xb2] _____________________
        except ValueError:
            parsed = None
            except ValueError:
                rl_port = 6379
            except ValueError:
                rl_db = 0
E                   ValueError: invalid literal for int() with base 10: '²'

src/groundx/extract/services/status.py:62: ValueError
=========================== short test summary info ============================
FAILED tests/extract/services/test_bite_claim.py::test_status_never_crashes[host:\xb2]
1 failed, 7 passed in 0.49s
```

## 2. 307c2373 fix(extract): derive Redis db from broker URL path, guarded (GX-33)

- What's wrong: The db guard claims any non-numeric path defaults to 0 with no crash, but a path like '/²' passes str.isdigit() and then makes int() raise ValueError.
- Today's code: fixed since
- Matters: 1/3
- Test: [307c2373_test_bite_claim.py](307c2373_test_bite_claim.py)
- Run it: copy it to `tests/extract/services/test_bite_claim.py`, then `python -m pytest -q -p no:cacheprovider tests/extract/services/test_bite_claim.py`

```
=================================== FAILURES ===================================
___________________ test_db_from_url[redis://h:6379/\xb2-0] ____________________
E           ValueError: invalid literal for int() with base 10: '²'

src/groundx/extract/services/status.py:38: ValueError
=========================== short test summary info ============================
FAILED tests/extract/services/test_bite_claim.py::test_db_from_url[redis://h:6379/\xb2-0]
1 failed, 5 passed in 0.51s
```

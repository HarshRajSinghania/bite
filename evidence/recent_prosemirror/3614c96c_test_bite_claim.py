import gc

from prosemirror.model import resolvedpos
from prosemirror.model.resolvedpos import ResolvedPos
from prosemirror.test_builder import out

doc = out["doc"]
p = out["p"]


def test_cache_entry_removed_after_doc_gc():
    resolvedpos._resolve_cache.clear()
    d = doc(p("hello"))
    ResolvedPos.resolve_cached(d, 2)
    assert len(resolvedpos._resolve_cache) == 1
    del d
    gc.collect()
    assert len(resolvedpos._resolve_cache) == 0

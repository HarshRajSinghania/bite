import gc, tracemalloc
from prosemirror.model import resolvedpos
from prosemirror.test_builder import out
doc, p = out["doc"], out["p"]
tracemalloc.start()
for i in range(20000):
    d = doc(p("hello world " * 20))
    d.resolve(5)          # the public API; same cache path
    del d
gc.collect()
print("cache entries after 20,000 docs were dropped:", len(resolvedpos._resolve_cache))
print("memory still held: %.1f MB" % (tracemalloc.get_traced_memory()[0] / 1e6))

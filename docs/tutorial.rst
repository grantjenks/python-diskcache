DiskCache Tutorial
==================

1. Document: core.Cache objects cannot be pickled.
2. Document: core.Cache objects do not survive os.fork.
3. Dcoument: core.Cache objects are thread-safe, but should be closed.
4. Document SQLite database restore trick using dump command and
   cache.check(fix=True).
5. Types matter in key equality comparisons. Comparisons like ``1 == 1.0`` and
   ``b'abc' == u'abc'`` are False.

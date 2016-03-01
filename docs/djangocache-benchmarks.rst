DiskCache DjangoCache Benchmarks
================================

1. filebased checks length on every set, scales linearly
   ~1000 files is 5ms, 1e5 files is 500ms.
   Also purges randomly.
   Show benchmark results.

Alternatives
------------

1. https://pypi.python.org/pypi/django-redis Very popular.
2. https://pypi.python.org/pypi/django-uwsgi-cache UWSGI cache backend.
3. https://github.com/atodorov/django-s3-cache S3-backend cache
   backend. Appears slow for large caches.
4. https://pypi.python.org/pypi/django-mongodb-cash-backend Cache backend
    support for MongoDB.
5. https://github.com/Suor/django-cacheops Does not provide CACHES
   backend. Custom file-based cache does no evictions on set. Relies instead on
   cron job.
6. http://django-cachalot.readthedocs.org/en/latest/benchmark.html Has
   benchmarks. Not sure how to interpret them.
7. http://pythonhosted.org/johnny-cache/localstore_cache.html Request-specific
   cache.
8. https://pypi.python.org/pypi/django-cacheback Solves stampede problem by
   off-loading computation to Celery.
9. https://pypi.python.org/pypi/django-newcache Claims to improve Django's
   memcached backend. Pretty small project. Thundering herd solution is
   strange... ignores timeout.
10. https://pypi.python.org/pypi/cache-tagging Supports tagging cache entries.

Processes = 8
-------------

========= ========= ========= ========= ========= ========= ========= =========
Timings for locmem
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get    712546    140750  35.048us  56.982us  60.081us   5.321ms  28.471s
      set     71530         0  36.955us  38.862us  45.061us   3.680ms   2.693s
   delete      7916         0  31.948us  34.809us  36.955us   1.036ms 259.096ms
    Total    791992                                                    31.424s
========= ========= ========= ========= ========= ========= ========= =========


========= ========= ========= ========= ========= ========= ========= =========
Timings for memcached
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get    712546     69176  87.023us  98.944us 112.057us 649.929us  61.850s
      set     71530         0  90.122us 102.997us 117.064us 608.206us   6.481s
   delete      7916         0  85.115us  97.036us 109.911us 211.000us 672.967ms
    Total    791992                                                    69.004s
========= ========= ========= ========= ========= ========= ========= =========


========= ========= ========= ========= ========= ========= ========= =========
Timings for redis
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get    712546     69262 163.078us 200.987us 240.088us   1.165ms 118.792s
      set     71530         0 169.992us 205.994us 245.094us 528.097us  12.390s
   delete      7916       786 147.104us 181.913us 219.822us 485.897us   1.192s
    Total    791992                                                   132.375s
========= ========= ========= ========= ========= ========= ========= =========


========= ========= ========= ========= ========= ========= ========= =========
Timings for diskcache
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get    712546     69891  54.121us  68.903us 108.004us  67.859ms  39.396s
      set     71530         0 350.952us 644.922us   2.295ms  65.822ms  35.388s
   delete      7916         0 252.962us 409.126us   1.690ms  19.295ms   2.744s
    Total    791992                                                    77.527s
========= ========= ========= ========= ========= ========= ========= =========


========= ========= ========= ========= ========= ========= ========= =========
Timings for filebased
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get    712143    112588  95.129us 144.958us 283.957us  26.260ms  75.667s
      set     71909         0   5.246ms   6.384ms   8.565ms  41.881ms 382.213s
   delete      7940         0 125.885us 226.974us 475.883us   2.939ms   1.176s
    Total    791992                                                   459.056s
========= ========= ========= ========= ========= ========= ========= =========

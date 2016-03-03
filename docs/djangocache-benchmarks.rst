DiskCache DjangoCache Benchmarks
================================

1. filebased checks length on every set, scales linearly
   ~1000 files is 5ms, 1e5 files is 500ms.
   Also purges randomly.
   Show benchmark results.

Cached Things
-------------

1. numbers (rankings),
2. processed text (8-128k),
3. list of labels (1-10 labels, 6-10 characters each)
4. cache html and javascript pages (60K, 300K)
5. list of settings (label, value pairs)
6. sets of numbers (dozens of integers)
7. QuerySets

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

.. image:: _static/djangocache-get.png

.. image:: _static/djangocache-set.png

.. image:: _static/djangocache-delete.png


========= ========= ========= ========= ========= ========= ========= =========
Timings for locmem
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get    712546    140750  35.048us  56.982us  59.128us  10.045ms  28.172s
      set     71530         0  36.955us  38.147us  43.154us   9.984ms   2.659s
   delete      7916         0  31.948us  34.094us  36.001us   9.987ms 267.255ms
    Total    791992                                                    31.099s
========= ========= ========= ========= ========= ========= ========= =========


========= ========= ========= ========= ========= ========= ========= =========
Timings for memcached
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get    712546     68969  87.976us 101.089us 113.010us 449.181us  62.615s
      set     71530         0  92.030us 105.143us 117.779us 442.982us   6.565s
   delete      7916         0  87.023us  99.897us 113.010us 206.947us 682.936ms
    Total    791992                                                    69.863s
========= ========= ========= ========= ========= ========= ========= =========


========= ========= ========= ========= ========= ========= ========= =========
Timings for redis
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get    712546     68854 171.900us 211.000us 250.101us   5.437ms 125.218s
      set     71530         0 179.052us 216.007us 255.108us   5.327ms  13.051s
   delete      7916       781 154.018us 190.020us 230.074us   1.309ms   1.253s
    Total    791992                                                   139.522s
========= ========= ========= ========= ========= ========= ========= =========


========= ========= ========= ========= ========= ========= ========= =========
Timings for diskcache
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get    712546     70313  50.068us  67.949us 102.043us  14.113ms  35.382s
      set     71530         0 355.005us   1.459ms   3.817ms  31.551ms  45.698s
   delete      7916         0 240.088us   1.330ms   3.665ms  26.498ms   3.785s
    Total    791992                                                    84.865s
========= ========= ========= ========= ========= ========= ========= =========


========= ========= ========= ========= ========= ========= ========= =========
Timings for filebased
-------------------------------------------------------------------------------
   Action     Count      Miss    Median       P90       P99       Max     Total
========= ========= ========= ========= ========= ========= ========= =========
      get    712580    123599  97.990us 144.958us 257.015us  15.342ms  75.490s
      set     71539         0   5.274ms   6.261ms   7.501ms  26.983ms 376.789s
   delete      7873         0 139.952us 235.081us 398.874us   1.394ms   1.218s
    Total    791992                                                   453.496s
========= ========= ========= ========= ========= ========= ========= =========


Filebased Cache
---------------

============ ============
Timings for glob.glob1
-------------------------
       Count         Time
============ ============
           1      1.602ms
          10      2.213ms
         100      8.946ms
        1000     65.869ms
       10000    604.972ms
      100000      6.450s
============ ============

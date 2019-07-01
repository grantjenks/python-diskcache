Case Study: Landing Page Caching
================================

:doc:`DiskCache <index>` version 4 added recipes for cache stampede mitigation.
Let's look at how that applies to landing page caching.

    >>> import time
    >>> def generate_landing_page():
    ...     time.sleep(0.2)  # Work really hard.
    ...     # Return HTML response.

Imagine a website under heavy load with a function used to generate the landing
page. There are two processes each with five threads for a total of ten
concurrent workers. Also assume that generating the landing page takes about
two hundred milliseconds.

.. image:: _static/no-caching.png

When we look at the number of concurrent workers and the latency with no
caching at all, the graph looks as above. Notice each worker constantly
regenerates the page with a consistently slow latency.

    >>> import diskcache as dc
    >>> cache = dc.Cache()
    >>> @cache.memoize(expire=1)
    ... def generate_landing_page():
    ...     time.sleep(0.2)

With traditional caching, the result of generating the landing page can be
memoized for one second. After each second, the cached HTML expires and all ten
workers rush to regenerate the result.

.. image:: _static/traditional-caching.png

There is a huge improvement in average latency now but some requests experience
worse latency than before due to the added overhead of caching. The cache
stampede is visible now as the spikes in the concurrency graph. If generating
the landing page requires significant resources then the spikes may be
prohibitive.

To reduce the number of concurrent workers, a barrier can be used to
synchronize generating the landing page::

    >>> @cache.memoize(expire=0)
    ... @dc.barrier(cache, dc.Lock)
    ... @cache.memoize(expire=1)
    ... def generate_landing_page():
    ...     time.sleep(0.2)

The double-checked locking uses two memoization decorators to optimistically
look up the cache result before locking.

.. image:: _static/synchronized-locking.png

.. image:: _static/early-recomputation.png

.. image:: _static/early-recomputation-05.png

.. image:: _static/early-recomputation-03.png

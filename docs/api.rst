DiskCache API Reference
=======================

The :doc:`tutorial` provides a helpful walkthrough of most methods.

DjangoCache
-----------

.. autoclass:: diskcache.DjangoCache
   :members:
   :special-members:

FanoutCache
-----------

.. autoclass:: diskcache.FanoutCache
   :members:
   :special-members:
   :exclude-members: __weakref__

Cache
-----

.. autoclass:: diskcache.Cache
   :members:
   :special-members:
   :exclude-members: __weakref__

Disk
----

.. autoclass:: diskcache.Disk
   :members:
   :special-members:
   :exclude-members: __weakref__

Constants
---------

.. data:: diskcache.DEFAULT_SETTINGS

   * `statistics` (int) default 0 - disabled when 0, enabled when 1.
   * `eviction_policy` (str) default "least-recently-stored" - any of the keys
     in `EVICTION_POLICY` as described below.
   * `size_limit` (int) default one gigabyte - approximate size limit of cache.
   * `cull_limit` (int) default ten - maximum number of keys culled during
     `set` operation.
   * `large_value_threshold` (int) default one kilobyte - values with greater
     size are stored in files.
   * `sqlite_synchronous` (str) default "NORMAL" - SQLite synchronous pragma.
   * `sqlite_journal_mode` (str) default "WAL" - SQLite journal mode pragma.
   * `sqlite_cache_size` (int) default 8,192 - SQLite cache size pragma.
   * `sqlite_mmap_size` (int) default 64 megabytes - SQLite mmap size pragma.

.. data:: diskcache.LIMITS

   * `min_int` (int) default ``-sys.maxsize - 1`` - smallest integer stored
     natively in SQLite.
   * `max_int` (int) default ``sys.maxsize`` - largest integer stored natively
     in SQLite.
   * `pragma_timeout` (int) default 60 - seconds to retry setting SQLite
     pragmas.

.. data:: diskcache.EVICTION_POLICY

   * `least-recently-stored` (default) - evict least recently stored keys first.
   * `least-recently-used` - evict least recently retrieved keys first.
   * `least-frequently-used` - evict least frequently used keys first.

Implementation Notes
--------------------

:doc:`DiskCache <index>` is mostly built on SQLite and the filesystem. Some
techniques used to improve performance:

* Shard database to distribute writes.
* Leverage SQLite native types: integers, floats, unicode, and bytes.
* Use SQLite write-ahead-log so reads and writes don't block each other.
* Use SQLite memory-mapped pages to accelerate reads.
* Store small values in SQLite database and large values in files.
* Always use a SQLite index for queries.
* Keep SQLite transactions short.
* Use SQLite triggers to maintain count of keys and size of database.

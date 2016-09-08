DiskCache API Reference
=======================

The :doc:`tutorial` provides a helpful walkthrough of most methods.

.. contents::
   :local:

DjangoCache
-----------

Read the :ref:`DjangoCache tutorial <tutorial-djangocache>` for example usage.

.. autoclass:: diskcache.DjangoCache
   :members:
   :special-members:

FanoutCache
-----------

Read the :ref:`FanoutCache tutorial <tutorial-fanoutcache>` for example usage.

.. autoclass:: diskcache.FanoutCache
   :members:
   :special-members:
   :exclude-members: __weakref__

Cache
-----

Read the :ref:`Cache tutorial <tutorial-cache>` for example usage.

.. autoclass:: diskcache.Cache
   :members:
   :special-members:
   :exclude-members: __weakref__

Constants
---------

Read the :ref:`Settings tutorial <tutorial-settings>` for details.

.. data:: diskcache.DEFAULT_SETTINGS

   * `statistics` (int) default 0 - disabled when 0, enabled when 1.
   * `tag_index` (int) default 0 - disabled when 0, enabled when 1.
   * `eviction_policy` (str) default "least-recently-stored" - any of the keys
     in `EVICTION_POLICY` as described below.
   * `size_limit` (int) default one gigabyte - approximate size limit of cache.
   * `cull_limit` (int) default ten - maximum number of items culled during
     `set` or `add` operations.
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
   * `least-recently-used` - evict least recently used keys first.
   * `least-frequently-used` - evict least frequently used keys first.

Disk
----

Read the :ref:`Disk tutorial <tutorial-disk>` for details.

.. autoclass:: diskcache.Disk
   :members:
   :special-members:
   :exclude-members: __weakref__

Timeout
-------

.. autoexception:: diskcache.Timeout

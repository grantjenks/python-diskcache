DiskCache Tutorial
==================

Installation
------------

This part of the documentation covers the installation of :doc:`DiskCache
<index>`.  The first step to using any software package is getting it properly
installed.

Pip & PyPI
..........

Installing :doc:`DiskCache <index>` is simple with `pip
<http://www.pip-installer.org/>`_::

    $ pip install diskcache

or, with `easy_install <http://pypi.python.org/pypi/setuptools>`_::

    $ easy_install diskcache

But, you really `shouldn't do that <http://www.pip-installer.org/en/latest/other-tools.html#pip-compared-to-easy-install>`_.

Get the Code
............

:doc:`DiskCache <index>` is actively developed on GitHub, where the code is
`always available <https://github.com/grantjenks/python-diskcache>`_.

You can either clone the public repository::

    $ git clone git://github.com/grantjenks/python-diskcache.git

Download the `tarball <https://github.com/grantjenks/python-diskcache/tarball/master>`_::

    $ curl -OL https://github.com/grantjenks/python-diskcache/tarball/master

Or, download the `zipball <https://github.com/grantjenks/python-diskcache/zipball/master>`_::

    $ curl -OL https://github.com/grantjenks/python-diskcache/zipball/master

Once you have a copy of the source, you can embed it in your Python package,
or install it into your site-packages easily::

    $ python setup.py install

:doc:`DiskCache <index>` is looking for a Debian package maintainer. Can you
help?

:doc:`DiskCache <index>` is looking for a CentOS/RPM package maintainer. Can
you help?

Cache
-----

The core of :doc:`DiskCache <index>` is :class:`diskcache.Cache` which
represents a disk and file backed cache. As a Cache it supports a familiar
Python Mapping interface with additional cache and performance parameters.

    >>> from diskcache import Cache
    >>> cache = Cache('mycachedir')

Initialization requires a directory path reference. If the directory path does
not exist, it will be created. Additional keyword parameters are discussed
below. Cache objects are thread-safe and may be shared between threads. Two
Cache objects may also reference the same directory from separate threads or
processes. In this way, they are also process-safe and support cross-process
communication.

When created, Cache objects open and maintain a file handle. As such, they may
not be pickled and do not survive process forking. Each thread that accesses a
cache is also responsible for calling :meth:`close <diskcache.Cache.close>` on
the cache if used. You can use a Cache reference in a `with` statement to
safeguard calling :meth:`close <diskcache.Cache.close>`.

    >>> cache.close()
    >>> with Cache('mycachedir') as reference:
    ...     pass

Set an item, get a value, and delete a key using the usual operators:

    >>> cache = Cache('mycachedir')
    >>> cache[b'key'] = b'value'
    >>> cache[b'key']
    'value'
    >>> b'key' in cache
    True
    >>> del cache[b'key']

There's also a :meth:`set <diskcache.Cache.set>` method with additional keyword
parameters: `expire`, `read`, and `tag`.

    >>> from io import BytesIO
    >>> cache.set(b'key', BytesIO('value'), expire=5, read=True, tag=u'data')
    True

In the example above: the key expires in 5 seconds, the value is read as a
file-like object, and tag metadata is stored with the key. Another method,
:meth:`get <diskcache.Cache.get>` supports querying extra information with
`default`, `read`, `expire_time`, and `tag` keyword parameters.

    >>> cache.get(b'key', default=b'', read=True, expire_time=True, tag=True)
    (<_io.BufferedReader
      name=u'mycachedir/1d/6e/128a921c3b8a9027c1f69989f3ac.val'>,
     1457066214.784396,
     u'data')

The return value is a tuple containing the value, expire time (seconds from
epoch), and tag. Because we passed ``read=True`` the value is returned as a
file-like object.

Another three methods remove items from the cache.

    >>> cache.cull_limit = 0              # Disable evictions.
    >>> for num in range(100):
    ...     cache.set(num, num, expire=0) # Expire immediately.
    >>> cache.cull_limit = 10
    >>> cache.expire()

:meth:`Expire <diskcache.Cache.expire>` removes all expired keys from the
cache. It does so in chunks according to the cull limit size.

    >>> for num in range(100):
    ...     cache.set(num, num, tag=u'odd' if num % 2 else u'even')
    >>> cache.evict(u'even')

:meth:`Evict <diskcache.Cache.evict>` removes all the keys with a matching
key. The default tag is ``None``. Tag values may be any of integer, float,
string, bytes and None.

    >>> cache.clear()

:meth:`Clear <diskcache.Cache.clear>` simply removes all keys from the
cache. Each of these methods is designed to work concurrent to others. None of
them lock or freeze the cache while operating.

Lastly, three methods support metadata about the cache. The first is
:meth:`volume <diskcache.Cache.volume>` which returns the estimated total size
in bytes of the cache directory on disk.

    >>> cache.volume()
    9216

The second is :meth:`stats <diskcache.Cache.stats>` which returns cache hits
and misses. Cache statistics must first be enabled.

    >>> cache.stats(enable=True)
    >>> for num in range(100):
    ...     cache.set(num, num)
    >>> for num in range(150):
    ...     cache.get(num)
    >>> cache.stats(enable=False, reset=True)
    (100, 50)

Cache statistics are useful when evaluating different eviction policies as
discussed below. By default, statistics are disabled as they incur an extra
overhead on cache retrieval.

The third is :meth:`check <diskcache.Cache.check>` which verifies cache
consistency. It can also fix inconsistencies and reclaimed unused space.

    >>> cache.check(fix=True)
    []

The value returned is a list of warnings. As such it is useful in assert
statements as ``assert len(cache.check()) == 0``.

FanoutCache
-----------

Built atop :class:`Cache <diskcache.Cache>` is :class:`diskcache.FanoutCache`
which automatically `shards` the underlying database used. `Sharding`_ is the
practice of horizontally partitioning data in a database. Here it is used to
decrease blocking writes. While readers and writers do not block each other,
writers block other writers. Therefore a shard for every concurrent writer is
suggested. This will depend on your scenario. The default value is 8.

Another parameter, `timeout`, sets a limit on how long to wait for database
operations. This depends on your requirements and underlying hardware. This
parameter is also present on :class:`diskcache.Cache` but operates differently
there. :class:`FanoutCache <diskcache.FanoutCache>` automatically catches
timeout errors and aborts the operation. This means that a :meth:`set
<diskcache.FanoutCache.set>` or :meth:`delete <diskcache.FanoutCache.delete>`
operation could fail to complete. The default value is 0.025 (25 milliseconds).

    >>> from diskcache import FanoutCache
    >>> cache = FanoutCache('mycachedir', shards=4, timeout=1)

The example above creates a cache in the local ``mycachedir`` directory with
four shards and a one second timeout. The `get`, `set`, and `delete` operations
will attempt to abort if they'll take longer than one second.

The remaining API of :class:`FanoutCache <diskcache.FanoutCache>` matches
:class:`Cache <diskcache.Cache>` as described above.

.. _`Sharding`: https://en.wikipedia.org/wiki/Shard_(database_architecture)

DjangoCache
-----------

:class:`diskcache.DjangoCache` uses :class:`FanoutCache
<diskcache.FanoutCache>` to provide a Django-compatible cache interface. With
:doc:`DiskCache <index>` installed, you can use :class:`DjangoCache
<diskcache.DjangoCache>` in your settings file.

::

    CACHES = {
        'default': {
            'BACKEND': 'diskcache.DjangoCache',
            'LOCATION': '/path/to/cache/directory',
            'SHARDS': 4,
            'DATABASE_TIMEOUT': 1.0,
            'OPTIONS': {
                'size_limit': 2 ** 32  # 4 gigabytes
            },
        },
    }

As with :class:`FanoutCache <diskcache.FanoutCache>` above, these settings
create a Django-compatible cache with four shards and a one second timeout. You
can pass further settings via the ``OPTIONS`` mapping as shown in the Django
documentation.

The API of :class:`DjangoCache <diskcache.DjangoCache>` is as described in the
`Django documentation on caching`_.

.. _`Django documentation on caching`: https://docs.djangoproject.com/en/1.9/topics/cache/#the-low-level-cache-api

Settings
--------

A variety of settings are available to improve performance. These values are
stored in the database for durability and to communicate between
processes. Each value is cached in an attribute with matching name. Attributes
are updated when set or deleted. Attributes are set during initialization when
passed as keyword arguments.

* `size_limit`, default one gigabyte. The maximum disk size of the cache.
* `cull_limit`, default ten. The maximum number of keys to cull when setting a
  new item. Set to zero to disable automatic culling. Some systems may disable
  automatic culling in exchange for a cron job that regularly calls
  :meth:`expire <diskcache.Cache.expire>` in a separate process.
* `large_value_threshold`, default one kilobyte. The minimum size of a value
  stored in a file on disk rather than in the cache database.
* `eviction_policy`, see section below.

    >>> cache = Cache('mycachedir', size_limit=int(4e9), cull_limit=2)
    >>> cache.size_limit
    4000000000
    >>> cache.cull_limit
    2
    >>> cache.large_value_threshold
    1024

An additional set of attributes correspond to SQLite pragmas. Changing these
values will also execute the appropriate ``PRAGMA`` statement. See the `SQLite
pragma documentation`_ for more details.

* `sqlite_synchronous`, default NORMAL.
* `sqlite_journal_mode`, default WAL.
* `sqlite_cache_size`, default 8,192 pages.
* `sqlite_mmap_size`, default 64 megabytes.

Each of these settings can passed to :class:`DjangoCache
<diskcache.DjangoCache>` via the ``OPTIONS`` key mapping. Always measure before
and after changing the default values. Default settings are programmatically
accessible at :data:`diskcache.DEFAULT_SETTINGS`.

.. _`SQLite pragma documentation`: https://www.sqlite.org/pragma.html

Eviction Policies
-----------------

:doc:`DiskCache <index>` supports three eviction policies each with different
tradeoffs for accessing and storing items.

* `Least Recently Stored` is the default. Every cache item records the time it
  was stored in the cache. This policy adds an index to that field. On access,
  no update is required. Keys are evicted starting with the oldest stored
  keys. As :doc:`DiskCache <index>` was intended for large caches (gigabytes)
  this policy usually works well enough in practice.
* `Least Recently Used` is the most commonly used policy. An index is added to
  the access time field stored in the cache database. On every access, the
  field is updated. This makes every access into a read and write which slows
  accesses.
* `Least Frequently Used` works well in some cases. An index is added to the
  access count field stored in the cache database. On every access, the field
  is incremented. Every access therefore requires writing the database which
  slows accesses.

All clients accessing the cache are expected to use the same eviction
policy. The policy can be set during initialization via keyword argument and
changed by attribute.

    >>> cache = Cache('mycachedir', eviction_policy=u'least-recently-used')
    >>> cache.eviction_policy
    u'least-recently-used'
    >>> cache.eviction_policy = u'least-frequently-used'
    >>> cache.eviction_policy = u'least-recently-stored'

The eviction policy can be changed at any time but previous indexes will not be
dropped.

Disk
----

:class:`diskcache.Disk` objects are responsible for serializing and
deserializing data stored in the cache. Serialization behavior differs between
keys and values. In particular, keys are always stored in the cache metadata
database while values are sometimes stored separately in files. To customize
serialization, you can pass in a :class:`Disk <diskcache.Disk>` object during
cache initialization. All clients accessing the cache are expected to use the
same serialization.

Four data types can be stored natively in the cache metadata database:
integers, floats, strings, and bytes. Other datatypes are converted to bytes
via the pickle protocol. Beware that integers and floats like ``1`` and ``1.0``
will compare equal as keys just as in Python. All other equality comparisons
will require identical types.

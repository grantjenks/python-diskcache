DiskCache Tutorial
==================

.. contents::
   :depth: 1
   :local:

Installation
------------

This part of the documentation covers the installation of :doc:`DiskCache
<index>`. The first step to using any software package is getting it properly
installed.

Pip & PyPI
..........

Installing :doc:`DiskCache <index>` is simple with `pip
<https://pip.pypa.io/en/stable/>`_::

    $ pip install diskcache

or, with `easy_install <https://setuptools.readthedocs.io/en/latest/easy_install.html>`_::

    $ easy_install diskcache

But `prefer pip <https://packaging.python.org/pip_easy_install/>`_ if at all
possible.

Get the Code
............

:doc:`DiskCache <index>` is actively developed on GitHub, where the code is
always available.

You can either clone the `DiskCache repository <https://github.com/grantjenks/python-diskcache>`_::

    $ git clone https://github.com/grantjenks/python-diskcache.git

Download the `tarball <https://github.com/grantjenks/python-diskcache/tarball/master>`_::

    $ curl -OL https://github.com/grantjenks/python-diskcache/tarball/master

Or, download the `zipball <https://github.com/grantjenks/python-diskcache/zipball/master>`_::

    $ curl -OL https://github.com/grantjenks/python-diskcache/zipball/master

Once you have a copy of the source, you can embed it in your Python package,
or install it into your site-packages easily::

    $ python setup.py install

:doc:`DiskCache <index>` is looking for a Debian package maintainer. If you can
help, please open an issue in the `DiskCache Issue Tracker
<https://github.com/grantjenks/python-diskcache/issues/>`_.

:doc:`DiskCache <index>` is looking for a CentOS/RPM package maintainer.  If
you can help, please open an issue in the `DiskCache Issue Tracker
<https://github.com/grantjenks/python-diskcache/issues/>`_.

.. _tutorial-cache:

Cache
-----

The core of :doc:`DiskCache <index>` is :class:`diskcache.Cache` which
represents a disk and file backed cache. As a Cache it supports a familiar
Python Mapping interface with additional cache and performance parameters.

    >>> from diskcache import Cache
    >>> cache = Cache('/tmp/mycachedir')

Initialization requires a directory path reference. If the directory path does
not exist, it will be created. Additional keyword parameters are discussed
below. Cache objects are thread-safe and may be shared between threads. Two
Cache objects may also reference the same directory from separate threads or
processes. In this way, they are also process-safe and support cross-process
communication.

When created, Cache objects open and maintain a file handle. As such, they do
not survive process forking but they may be serialized using Pickle. Each
thread that accesses a cache is also responsible for calling :meth:`close
<diskcache.Cache.close>` on the cache. You can use a Cache reference in a
`with` statement to safeguard calling :meth:`close <diskcache.Cache.close>`.

    >>> cache.close()
    >>> with Cache('/tmp/mycachedir') as reference:
    ...     pass

Set an item, get a value, and delete a key using the usual operators:

    >>> cache = Cache('/tmp/mycachedir')
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
      name=u'/tmp/mycachedir/1d/6e/128a921c3b8a9027c1f69989f3ac.val'>,
     1457066214.784396,
     u'data')

The return value is a tuple containing the value, expire time (seconds from
epoch), and tag. Because we passed ``read=True`` the value is returned as a
file-like object.

Like :meth:`set <diskcache.Cache.set>`, the method :meth:`add
<diskcache.Cache.add>` can be used to insert an item in the cache. The item is
inserted only if the key is not already present.

    >>> cache.add(b'test', 123)
    True
    >>> cache[b'test']
    123
    >>> cache.add(b'test', 456)
    False
    >>> cache[b'test']
    123

Item values can also be incremented and decremented using :meth:`incr
<diskcache.Cache.incr>` and :meth:`decr <diskcache.Cache.decr>` methods.

    >>> cache.incr(b'test')
    124
    >>> cache.decr(b'test', 24)
    100

Increment and decrement methods also support a keyword parameter, `default`,
which will be used for missing keys. When ``None``, incrementing or
decrementing a missing key will raise a :exc:`KeyError`.

    >>> cache.incr(u'alice')
    1
    >>> cache.decr(u'bob', default=-9)
    -10
    >>> cache.incr(u'carol', default=None)
    Traceback (most recent call last):
        ...
    KeyError: u'carol'

Increment and decrement operations are atomic and assume the value may be
stored in a SQLite column. Most builds that target machines with 64-bit pointer
widths will support 64-bit signed integers.

Like :meth:`delete <diskcache.Cache.delete>` and :meth:`get
<diskcache.Cache.get>`, the method :meth:`pop <diskcache.Cache.pop>` can be
used to delete an item in the cache and return its value.

    >>> cache.pop(u'alice')
    1
    >>> cache.pop(u'dave', default=u'does not exist')
    u'does not exist'
    >>> cache.set(u'dave', 0, expire=None, tag=u'admin')
    >>> cache.pop(u'dave', expire_time=True, tag=True)
    (0, None, u'admin')

The :meth:`pop <diskcache.Cache.pop>` operation is atomic and using :meth:`incr
<diskcache.Cache.incr>` together is an accurate method for counting and dumping
statistics in long-running systems. Unlike :meth:`get <diskcache.Cache.get>`
the `read` argument is not supported.

Another three methods remove items from the cache.

    >>> cache.reset('cull_limit', 0)       # Disable automatic evictions.
    >>> for num in range(10):
    ...     cache.set(num, num, expire=0)  # Expire immediately.
    >>> len(cache)
    10
    >>> list(cache)
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    >>> cache.expire()
    10

:meth:`Expire <diskcache.Cache.expire>` removes all expired keys from the
cache. Resetting the `cull_limit` to zero will disable culling during
:meth:`set <diskcache.Cache.set>` and :meth:`add <diskcache.Cache.add>`
operations. Because culling is performed lazily, the reported length of the
cache includes expired items. Iteration likewise includes expired items because
it is a read-only operation. To exclude expired items you must explicitly call
:meth:`expire <diskcache.Cache.expire>` which works regardless of the
`cull_limit`.

    >>> for num in range(100):
    ...     cache.set(num, num, tag=u'odd' if num % 2 else u'even')
    >>> cache.evict(u'even')

.. _tutorial-tag-index:

:meth:`Evict <diskcache.Cache.evict>` removes all the keys with a matching
tag. The default tag is ``None``. Tag values may be any of integer, float,
string, bytes and None. To accelerate the eviction of items by tag, an index
can be created. To do so, initialize the cache with ``tag_index=True``.

    >>> cache = Cache('/tmp/mycachedir', tag_index=True)
    >>> for num in range(100):
    ...     cache.set(num, num, tag=(num % 2))
    >>> cache.evict(0)

Likewise, the tag index may be created or dropped using methods::

    >>> cache.drop_tag_index()
    >>> cache.tag_index
    0
    >>> cache.create_tag_index()
    >>> cache.tag_index
    1

But prefer initializing the cache with a tag index rather than explicitly
creating or dropping the tag index.

:meth:`Clear <diskcache.Cache.clear>` simply removes all items from the cache.

    >>> cache.clear()

Each of these methods is designed to work concurrent to others. None of them
block readers or writers in other threads or processes.

Lastly, three methods support metadata about the cache. The first is
:meth:`volume <diskcache.Cache.volume>` which returns the estimated total size
in bytes of the cache directory on disk.

    >>> cache.volume()
    9216

.. _tutorial-statistics:

The second is :meth:`stats <diskcache.Cache.stats>` which returns cache hits
and misses. Cache statistics must first be enabled.

    >>> cache.stats(enable=True)
    (0, 0)
    >>> for num in range(100):
    ...     cache.set(num, num)
    >>> for num in range(150):
    ...     cache.get(num)
    >>> cache.stats(enable=False, reset=True)
    (100, 50)  # 100 hits, 50 misses

Cache statistics are useful when evaluating different :ref:`eviction policies
<tutorial-eviction-policies>`. By default, statistics are disabled as they
incur an extra overhead on cache lookups. Increment and decrement operations
are not counted in cache statistics.

The third is :meth:`check <diskcache.Cache.check>` which verifies cache
consistency. It can also fix inconsistencies and reclaim unused space.

    >>> cache.check(fix=True)
    []

The return value is a list of warnings.

.. _tutorial-fanoutcache:

FanoutCache
-----------

Built atop :class:`Cache <diskcache.Cache>` is :class:`diskcache.FanoutCache`
which automatically `shards` the underlying database. `Sharding`_ is the
practice of horizontally partitioning data. Here it is used to decrease
blocking writes. While readers and writers do not block each other, writers
block other writers. Therefore a shard for every concurrent writer is
suggested. This will depend on your scenario. The default value is 8.

Another parameter, `timeout`, sets a limit on how long to wait for database
transactions. Transactions are used for every operation that writes to the
database. The `timeout` parameter is also present on
:class:`diskcache.Cache`. When a :exc:`diskcache.Timeout` error occurs in
:class:`Cache <diskcache.Cache>` methods, the exception is raised to the
caller. In contrast, :class:`FanoutCache <diskcache.FanoutCache>` catches
timeout errors and aborts the operation. As a result, :meth:`set
<diskcache.FanoutCache.set>` and :meth:`delete <diskcache.FanoutCache.delete>`
methods may silently fail. Most methods that handle :exc:`Timeout
<diskcache.Timeout>` exceptions also include a `retry` keyword parameter
(default ``False``) to automatically repeat attempts that
timeout. :class:`FanoutCache <diskcache.FanoutCache>` will never raise a
:exc:`Timeout <diskcache.Timeout>` exception. The default `timeout` is 0.025
(25 milliseconds).

    >>> from diskcache import FanoutCache
    >>> cache = FanoutCache('/tmp/mycachedir', shards=4, timeout=1)

The example above creates a cache in the local ``/tmp/mycachedir`` directory
with four shards and a one second timeout. Operations will attempt to abort if
they take longer than one second. The remaining API of :class:`FanoutCache
<diskcache.FanoutCache>` matches :class:`Cache <diskcache.Cache>` as described
above.

:class:`FanoutCache <diskcache.FanoutCache>` adds an additional feature:
:meth:`memoizing <diskcache.FanoutCache.memoize>` cache decorator. The
decorator wraps a callable and caches arguments and return values.

    >>> from diskcache import FanoutCache
    >>> cache = FanoutCache('/tmp/diskcache/fanoutcache')
    >>> @cache.memoize(typed=True, expire=1, tag='fib')
    ... def fibonacci(number):
    ...     if number == 0:
    ...         return 0
    ...     elif number == 1:
    ...         return 1
    ...     else:
    ...         return fibonacci(number - 1) + fibonacci(number - 2)
    >>> print(sum(fibonacci(number=value) for value in range(100)))
    573147844013817084100

The arguments to memoize are like those for `functools.lru_cache
<https://docs.python.org/3/library/functools.html#functools.lru_cache>`_ and
:meth:`FanoutCache.set <diskcache.FanoutCache.set>`. Remember to call
:meth:`memoize <diskcache.FanoutCache.memoize>` when decorating a callable. If
you forget, then a TypeError will occur.

    >>> @cache.memoize
    ... def test():
    ...     pass
    Traceback (most recent call last):
        ...
    TypeError: name cannot be callable

Observe the lack of parenthenses after :meth:`memoize
<diskcache.FanoutCache.set>` above.

.. _`Sharding`: https://en.wikipedia.org/wiki/Shard_(database_architecture)

.. _tutorial-djangocache:

DjangoCache
-----------

:class:`diskcache.DjangoCache` uses :class:`FanoutCache
<diskcache.FanoutCache>` to provide a Django-compatible cache interface. With
:doc:`DiskCache <index>` installed, you can use :class:`DjangoCache
<diskcache.DjangoCache>` in your settings file.

.. code-block:: python

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
documentation. :class:`DjangoCache <diskcache.DjangoCache>` will never raise a
:exc:`Timeout <diskcache.Timeout>` exception. But unlike :class:`FanoutCache
<diskcache.FanoutCache>`, the keyword parameter `retry` defaults to ``True``
for :class:`DjangoCache <diskcache.DjangoCache>` methods.

The API of :class:`DjangoCache <diskcache.DjangoCache>` is a superset of the
functionality described in the `Django documentation on caching`_ and includes
many :class:`FanoutCache <diskcache.FanoutCache>` features.

:class:`DjangoCache <diskcache.DjangoCache>` also works well with `X-Sendfile`
and `X-Accel-Redirect` headers.

.. code-block:: python

    from django.core.cache import cache

    def media(request, path):
        try:
            with cache.read(path) as reader:
                response = HttpResponse()
                response['X-Accel-Redirect'] = reader.name
                return response
        except KeyError:
            # Handle cache miss.

When values are :meth:`set <diskcache.DjangoCache.set>` using ``read=True``
they are guaranteed to be stored in files. The full path is available on the
file handle in the `name` attribute. Remember to also include the
`Content-Type` header if known.

.. _`Django documentation on caching`: https://docs.djangoproject.com/en/1.9/topics/cache/#the-low-level-cache-api

Deque
-----

:class:`diskcache.Deque` (pronounced "deck") uses a :class:`Cache
<diskcache.Cache>` to provide a `collections.deque
<https://docs.python.org/3/library/collections.html#collections.deque>`_-compatible
double-ended queue. Deques are a generalization of stacks and queues with fast
access and editing at both front and back sides. :class:`Deque
<diskcache.Deque>` objects inherit the benefits of the :class:`Cache
<diskcache.Cache>` objects but never evict items.

    >>> from diskcache import Deque
    >>> deque = Deque(range(5, 10))
    >>> deque.pop()
    9
    >>> deque.popleft()
    5
    >>> deque.appendleft('foo')
    >>> len(deque)
    4
    >>> deque.directory
    '/tmp/...'
    >>> other = Deque(directory=deque.directory)
    >>> len(other)
    4
    >>> other.popleft()
    'foo'

:class:`Deque <diskcache.Deque>` objects provide an efficient and safe means of
cross-thread and cross-process communication. :class:`Deque <diskcache.Deque>`
objects are also useful in scenarios where contents should remain persistent or
limitations prohibit holding all items in memory at the same time.

Index
-----

:class:`diskcache.Index` uses a :class:`Cache <diskcache.Cache>` to provide a
`mutable mapping
<https://docs.python.org/3/library/collections.abc.html#collections-abstract-base-classes>`_
and `ordered dictionary
<https://docs.python.org/3/library/collections.html#collections.OrderedDict>`_
interface. :class:`Index <diskcache.Index>` objects inherit the benefits of
:class:`Cache <diskcache.Cache>` objects but never evict items.

    >>> from diskcache import Index
    >>> index = Index([('a', 1), ('b', 2), ('c', 3)])
    >>> 'b' in index
    True
    >>> index['c']
    3
    >>> del index['a']
    >>> len(index)
    2
    >>> other = Index(index.directory)
    >>> len(other)
    2
    >>> other.popitem(last=False)
    ('b', 2)

:class:`Index <diskcache.Index>` objects provide an efficient and safe means of
cross-thread and cross-process communication. :class:`Index <diskcache.Index>`
objects are also useful in scenarios where contents should remain persistent or
limitations prohibit holding all items in memory at the same time.

.. _tutorial-settings:

Settings
--------

A variety of settings are available to improve performance. These values are
stored in the database for durability and to communicate between
processes. Each value is cached in an attribute with matching name. Attributes
are updated using :meth:`reset <diskcache.Cache.reset>`. Attributes are set
during initialization when passed as keyword arguments.

* `size_limit`, default one gigabyte. The maximum on-disk size of the cache.
* `cull_limit`, default ten. The maximum number of keys to cull when adding a
  new item. Set to zero to disable automatic culling. Some systems may disable
  automatic culling in exchange for a cron-like job that regularly calls
  :meth:`expire <diskcache.DjangoCache.expire>` in a separate process.
* `statistics`, default False, disabled. The setting to collect :ref:`cache
  statistics <tutorial-statistics>`.
* `tag_index`, default False, disabled. The setting to create a database
  :ref:`tag index <tutorial-tag-index>` for :meth:`evict
  <diskcache.Cache.evict>`.
* `eviction_policy`, default "least-recently-stored". The setting to determine
  :ref:`eviction policy <tutorial-eviction-policies>`.

The :meth:`reset <diskcache.FanoutCache.reset>` method accepts an optional
second argument that updates the corresponding value in the database. The
return value is the latest retrieved from the database. Notice that attributes
are updated lazily. Prefer idioms like :meth:`len
<diskcache.FanoutCache.__len__>`, :meth:`volume
<diskcache.FanoutCache.volume>`, and :meth:`keyword arguments
<diskcache.FanoutCache.__init__>` rather than using :meth:`reset
<diskcache.FanoutCache.reset>` directly.

    >>> cache = Cache('/tmp/mycachedir', size_limit=int(4e9))
    >>> cache.size_limit
    4000000000
    >>> cache.disk_min_file_size
    1024
    >>> cache.reset('cull_limit', 0)  # Disable automatic evictions.
    0
    >>> cache.set(b'key', 1.234)
    True
    >>> cache.count           # Stale attribute.
    0
    >>> cache.reset('count')  # Prefer: len(cache)
    1

More settings correspond to :ref:`Disk <tutorial-disk>` attributes. Each of
these may be specified when initializing the :ref:`Cache
<tutorial-cache>`. Changing these values will update the unprefixed attribute
on the :class:`Disk <diskcache.Disk>` object.

* `disk_min_file_size`, default one kilobyte. The minimum size to store a value
  in a file.
* `disk_pickle_protocol`, default highest Pickle protocol. The Pickle protocol
  to use for data types that are not natively supported.

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

.. _tutorial-eviction-policies:

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
policy. The policy can be set during initialization using a keyword argument.

    >>> cache = Cache('/tmp/mydir')
    >>> cache.eviction_policy
    u'least-recently-stored'
    >>> cache = Cache('/tmp/mydir', eviction_policy=u'least-frequently-used')
    >>> cache.eviction_policy
    u'least-frequently-used'
    >>> cache.reset('eviction_policy', u'least-recently-used')
    u'least-recently-used'

Though the eviction policy is changed, the previously created indexes will not
be dropped. Prefer to always specify the eviction policy as a keyword argument
to initialize the cache.

.. _tutorial-disk:

Disk
----

:class:`diskcache.Disk` objects are responsible for serializing and
deserializing data stored in the cache. Serialization behavior differs between
keys and values. In particular, keys are always stored in the cache metadata
database while values are sometimes stored separately in files.

To customize serialization, you may pass in a :class:`Disk <diskcache.Disk>`
subclass to initialize the cache. All clients accessing the cache are expected
to use the same serialization. The default implementation uses Pickle and the
example below uses compressed JSON.

.. code-block:: python

    import json, zlib

    class JSONDisk(diskcache.Disk):
        def __init__(self, directory, compress_level=1, **kwargs):
            self.compress_level = compress_level
            super(JSONDisk, self).__init__(directory, **kwargs)

        def put(self, key):
            json_bytes = json.dumps(key).encode('utf-8')
            data = zlib.compress(json_bytes, self.compress_level)
            return super(JSONDisk, self).put(data)

        def get(self, key, raw):
            data = super(JSONDisk, self).get(key, raw)
            return json.loads(zlib.decompress(data).decode('utf-8'))

        def store(self, value, read):
            if not read:
                json_bytes = json.dumps(value).encode('utf-8')
                value = zlib.compress(json_bytes, self.compress_level)
            return super(JSONDisk, self).store(value, read)

        def fetch(self, mode, filename, value, read):
            data = super(JSONDisk, self).fetch(mode, filename, value, read)
            if not read:
                data = json.loads(zlib.decompress(data).decode('utf-8'))
            return data

    with Cache('/tmp/dir', disk=JSONDisk, disk_compress_level=6) as cache:
        pass

Four data types can be stored natively in the cache metadata database:
integers, floats, strings, and bytes. Other datatypes are converted to bytes
via the Pickle protocol. Beware that integers and floats like ``1`` and ``1.0``
will compare equal as keys just as in Python. All other equality comparisons
will require identical types.

Caveats
-------

Though :doc:`DiskCache <index>` has a dictionary-like interface, Python's `hash
protocol`_ is not used. Neither the `__hash__` nor `__eq__` methods are used
for lookups. Instead lookups depend on the serialization method defined by
:class:`Disk <diskcache.Disk>` objects. For strings, bytes, integers, and
floats, equality matches Python's definition. But large integers and all other
types will be converted to bytes using pickling and the bytes representation
will define equality.

:doc:`DiskCache <index>` uses SQLite to synchronize database access between
threads and processes and as such inherits all SQLite caveats. Most notably
SQLite is `not recommended`_ for use with Network File System (NFS) mounts. For
this reason, :doc:`DiskCache <index>` currently `performs poorly`_ on `Python
Anywhere`_.

.. _`hash protocol`: https://docs.python.org/library/functions.html#hash
.. _`not recommended`: https://www.sqlite.org/faq.html#q5
.. _`performs poorly`: https://www.pythonanywhere.com/forums/topic/1847/
.. _`Python Anywhere`: https://www.pythonanywhere.com/

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
* Use SQLite triggers to maintain key count and database size.

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

    $ pip install --upgrade diskcache

The versioning scheme uses `major.minor.micro` with `micro` intended for bug
fixes, `minor` intended for small features or improvements, and `major`
intended for significant new features and breaking changes. While it is
intended that only `major` version changes are backwards incompatible, it is
not always guaranteed. When running in production, it is recommended to pin at
least the `major` version.

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
help, please open an issue in the `DiskCache Issue Tracker`_.

:doc:`DiskCache <index>` is looking for a CentOS/RPM package maintainer. If you
can help, please open an issue in the `DiskCache Issue Tracker`_.

.. _`DiskCache Issue Tracker`: https://github.com/grantjenks/python-diskcache/issues/

.. _tutorial-cache:

Cache
-----

The core of :doc:`DiskCache <index>` is :class:`diskcache.Cache` which
represents a disk and file backed cache. As a Cache, it supports a familiar
Python mapping interface with additional cache and performance parameters.

    >>> from diskcache import Cache
    >>> cache = Cache()

Initialization expects a directory path reference. If the directory path does
not exist, it will be created. When not specified, a temporary directory is
automatically created. Additional keyword parameters are discussed below. Cache
objects are thread-safe and may be shared between threads. Two Cache objects
may also reference the same directory from separate threads or processes. In
this way, they are also process-safe and support cross-process communication.

Cache objects open and maintain one or more file handles. But unlike files, all
Cache operations are atomic and Cache objects support process-forking and may
be serialized using Pickle. Each thread that accesses a cache should also call
:meth:`close <.Cache.close>` on the cache. Cache objects can be used
in a `with` statement to safeguard calling :meth:`close
<diskcache.Cache.close>`.

    >>> cache.close()
    >>> with Cache(cache.directory) as reference:
    ...     reference.set('key', 'value')
    True

Closed Cache objects will automatically re-open when accessed. But opening
Cache objects is relatively slow, and since all operations are atomic, may be
safely left open.

    >>> cache.close()
    >>> cache.get('key')  # Automatically opens, but slower.
    'value'

Set an item, get a value, and delete a key using the usual operators:

    >>> cache['key'] = 'value'
    >>> cache['key']
    'value'
    >>> 'key' in cache
    True
    >>> del cache['key']

There's also a :meth:`set <diskcache.Cache.set>` method with additional keyword
parameters: `expire`, `read`, and `tag`.

    >>> from io import BytesIO
    >>> cache.set('key', BytesIO(b'value'), expire=5, read=True, tag='data')
    True

In the example above: the key expires in 5 seconds, the value is read as a
file-like object, and tag metadata is stored with the key. Another method,
:meth:`get <diskcache.Cache.get>` supports querying extra information with
`default`, `read`, `expire_time`, and `tag` keyword parameters.

    >>> result = cache.get('key', read=True, expire_time=True, tag=True)
    >>> reader, timestamp, tag = result
    >>> print(reader.read().decode())
    value
    >>> type(timestamp).__name__
    'float'
    >>> print(tag)
    data

The return value is a tuple containing the value, expire time (seconds from
epoch), and tag. Because we passed ``read=True`` the value is returned as a
file-like object.

Use :meth:`touch <.Cache.touch>` to update the expiration time of an item in
the cache.

    >>> cache.touch('key', expire=None)
    True
    >>> cache.touch('does-not-exist', expire=1)
    False

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

    >>> cache.incr('alice')
    1
    >>> cache.decr('bob', default=-9)
    -10
    >>> cache.incr('carol', default=None)
    Traceback (most recent call last):
        ...
    KeyError: 'carol'

Increment and decrement operations are atomic and assume the value may be
stored in a SQLite integer column. SQLite supports 64-bit signed integers.

Like :meth:`delete <diskcache.Cache.delete>` and :meth:`get
<diskcache.Cache.get>`, the method :meth:`pop <diskcache.Cache.pop>` can be
used to delete an item in the cache and return its value.

    >>> cache.pop('alice')
    1
    >>> cache.pop('dave', default='does not exist')
    'does not exist'
    >>> cache.set('dave', 0, expire=None, tag='admin')
    True
    >>> result = cache.pop('dave', expire_time=True, tag=True)
    >>> value, timestamp, tag = result
    >>> value
    0
    >>> print(timestamp)
    None
    >>> print(tag)
    admin

The :meth:`pop <diskcache.Cache.pop>` operation is atomic and using :meth:`incr
<diskcache.Cache.incr>` together is an accurate method for counting and dumping
statistics in long-running systems. Unlike :meth:`get <diskcache.Cache.get>`
the `read` argument is not supported.

.. _tutorial-culling:

Another four methods remove items from the cache::

    >>> cache.clear()
    3
    >>> cache.reset('cull_limit', 0)       # Disable automatic evictions.
    0
    >>> for num in range(10):
    ...     _ = cache.set(num, num, expire=1e-9)  # Expire immediately.
    >>> len(cache)
    10
    >>> list(cache)
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    >>> import time
    >>> time.sleep(1)
    >>> cache.expire()
    10

:meth:`Expire <diskcache.Cache.expire>` removes all expired keys from the
cache. Resetting the :ref:`cull_limit <tutorial-settings>` to zero will disable
culling during :meth:`set <diskcache.Cache.set>` and :meth:`add
<diskcache.Cache.add>` operations. Because culling is performed lazily, the
reported length of the cache includes expired items. Iteration likewise
includes expired items because it is a read-only operation. To exclude expired
items you must explicitly call :meth:`expire <diskcache.Cache.expire>` which
works regardless of the :ref:`cull_limit <tutorial-settings>`.

    >>> for num in range(100):
    ...     _ = cache.set(num, num, tag='odd' if num % 2 else 'even')
    >>> cache.evict('even')
    50

.. _tutorial-tag-index:

:meth:`Evict <diskcache.Cache.evict>` removes all the keys with a matching
tag. The default tag is ``None``. Tag values may be any of integer, float,
string, bytes and None. To accelerate the eviction of items by tag, an index
can be created. To do so, initialize the cache with ``tag_index=True``.

    >>> cache.clear()
    50
    >>> for num in range(100):
    ...     _ = cache.set(num, num, tag=(num % 2))
    >>> cache.evict(0)
    50

Likewise, the tag index may be created or dropped using methods::

    >>> cache.drop_tag_index()
    >>> cache.tag_index
    0
    >>> cache.create_tag_index()
    >>> cache.tag_index
    1

But prefer initializing the cache with a tag index rather than explicitly
creating or dropping the tag index.

To manually enforce the cache's size limit, use the :meth:`cull
<diskcache.Cache.cull>` method. :meth:`Cull <diskcache.Cache.cull>` begins by
removing expired items from the cache and then uses the eviction policy to
remove items until the cache volume is less than the size limit.

    >>> cache.clear()
    50
    >>> cache.reset('size_limit', int(1e6))
    1000000
    >>> cache.reset('cull_limit', 0)
    0
    >>> for count in range(1000):
    ...     cache[count] = b'A' * 1000
    >>> cache.volume() > int(1e6)
    True
    >>> cache.cull() > 0
    True
    >>> cache.volume() < int(1e6)
    True

Some users may defer all culling to a cron-like process by setting the
:ref:`cull_limit <tutorial-settings>` to zero and manually calling :meth:`cull
<diskcache.Cache.cull>` to remove items. Like :meth:`evict
<diskcache.Cache.evict>` and :meth:`expire <diskcache.Cache.expire>`, calls to
:meth:`cull <diskache.Cache.cull>` will work regardless of the :ref:`cull_limit
<tutorial-settings>`.

:meth:`Clear <diskcache.Cache.clear>` simply removes all items from the cache.

    >>> cache.clear() > 0
    True

Each of these methods is designed to work concurrent to others. None of them
block readers or writers in other threads or processes.

Caches may be iterated by either insertion order or sorted order. The default
ordering uses insertion order. To iterate by sorted order, use :meth:`iterkeys
<.Cache.iterkeys>`. The sort order is determined by the database which makes it
valid only for `str`, `bytes`, `int`, and `float` data types. Other types of
keys will be serialized which is likely to have a meaningless sorted order.

    >>> for key in 'cab':
    ...     cache[key] = None
    >>> list(cache)
    ['c', 'a', 'b']
    >>> list(cache.iterkeys())
    ['a', 'b', 'c']
    >>> cache.peekitem()
    ('b', None)
    >>> cache.peekitem(last=False)
    ('c', None)

If only the first or last item in insertion order is desired then
:meth:`peekitem <.Cache.peekitem>` is more efficient than using iteration.

Three additional methods use the sorted ordering of keys to maintain a
queue-like data structure within the cache. The :meth:`push <.Cache.push>`,
:meth:`pull <.Cache.pull>`, and :meth:`peek <.Cache.peek>` methods
automatically assign the key within the cache.

    >>> key = cache.push('first')
    >>> print(key)
    500000000000000
    >>> cache[key]
    'first'
    >>> _ = cache.push('second')
    >>> _ = cache.push('zeroth', side='front')
    >>> _, value = cache.peek()
    >>> value
    'zeroth'
    >>> key, value = cache.pull()
    >>> print(key)
    499999999999999
    >>> value
    'zeroth'

The `side` parameter supports access to either the ``'front'`` or ``'back'`` of
the cache. In addition, the `prefix` parameter can be used to maintain multiple
queue-like data structures within a single cache. When prefix is ``None``,
integer keys are used. Otherwise, string keys are used in the format
“prefix-integer”. Integer starts at 500 trillion. Like :meth:`set <.Cache.set>`
and :meth:`get <.Cache.get>`, methods :meth:`push <.Cache.push>`, :meth:`pull
<.Cache.pull>`, and :meth:`peek <.Cache.peek>` support cache metadata like the
expiration time and tag.

Lastly, three methods support metadata about the cache. The first is
:meth:`volume <diskcache.Cache.volume>` which returns the estimated total size
in bytes of the cache directory on disk.

    >>> cache.volume() < int(1e5)
    True

.. _tutorial-statistics:

The second is :meth:`stats <diskcache.Cache.stats>` which returns cache hits
and misses. Cache statistics must first be enabled.

    >>> cache.stats(enable=True)
    (0, 0)
    >>> for num in range(100):
    ...     _ = cache.set(num, num)
    >>> for num in range(150):
    ...     _ = cache.get(num)
    >>> hits, misses = cache.stats(enable=False, reset=True)
    >>> (hits, misses)
    (100, 50)

Cache statistics are useful when evaluating different :ref:`eviction policies
<tutorial-eviction-policies>`. By default, statistics are disabled as they
incur an extra overhead on cache lookups. Increment and decrement operations
are not counted in cache statistics.

The third is :meth:`check <diskcache.Cache.check>` which verifies cache
consistency. It can also fix inconsistencies and reclaim unused space. The
return value is a list of warnings.

    >>> warnings = cache.check()

Caches do not automatically remove the underlying directory where keys and
values are stored. The cache is intended to be persistent and so must be
deleted manually.

    >>> cache.close()
    >>> import shutil
    >>> try:
    ...     shutil.rmtree(cache.directory)
    ... except OSError:  # Windows wonkiness
    ...     pass

To permanently delete the cache, recursively remove the cache's directory.

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
database. When the timeout expires, a :exc:`diskcache.Timeout` error is raised
internally. This `timeout` parameter is also present on
:class:`diskcache.Cache`. When a :exc:`Timeout <diskcache.Timeout>` error
occurs in :class:`Cache <diskcache.Cache>` methods, the exception may be raised
to the caller. In contrast, :class:`FanoutCache <diskcache.FanoutCache>`
catches all timeout errors and aborts the operation. As a result, :meth:`set
<diskcache.FanoutCache.set>` and :meth:`delete <diskcache.FanoutCache.delete>`
methods may silently fail.

Most methods that handle :exc:`Timeout <diskcache.Timeout>` exceptions also
include a `retry` keyword parameter (default ``False``) to automatically repeat
attempts that timeout. The mapping interface operators: :meth:`cache[key]
<diskcache.FanoutCache.__getitem__>`, :meth:`cache[key] = value
<diskcache.FanoutCache.__setitem__>`, and :meth:`del cache[key]
<diskcache.FanoutCache.__delitem__>` automatically retry operations when
:exc:`Timeout <diskcache.Timeout>` errors occur. :class:`FanoutCache
<diskcache.FanoutCache>` will never raise a :exc:`Timeout <diskcache.Timeout>`
exception. The default `timeout` is 0.010 (10 milliseconds).

    >>> from diskcache import FanoutCache
    >>> cache = FanoutCache(shards=4, timeout=1)

The example above creates a cache in a temporary directory with four shards and
a one second timeout. Operations will attempt to abort if they take longer than
one second. The remaining API of :class:`FanoutCache <diskcache.FanoutCache>`
matches :class:`Cache <diskcache.Cache>` as described above.

The :class:`.FanoutCache` :ref:`size_limit <constants>` is used as the total
size of the cache. The size limit of individual cache shards is the total size
divided by the number of shards. In the example above, the default total size
is one gigabyte and there are four shards so each cache shard has a size limit
of 256 megabytes. Items that are larger than the size limit are immediately
culled.

Caches have an additional feature: :meth:`memoizing
<diskcache.FanoutCache.memoize>` decorator. The decorator wraps a callable and
caches arguments and return values.

    >>> from diskcache import FanoutCache
    >>> cache = FanoutCache()
    >>> @cache.memoize(typed=True, expire=1, tag='fib')
    ... def fibonacci(number):
    ...     if number == 0:
    ...         return 0
    ...     elif number == 1:
    ...         return 1
    ...     else:
    ...         return fibonacci(number - 1) + fibonacci(number - 2)
    >>> print(sum(fibonacci(value) for value in range(100)))
    573147844013817084100

The arguments to memoize are like those for `functools.lru_cache
<https://docs.python.org/3/library/functools.html#functools.lru_cache>`_ and
:meth:`Cache.set <.Cache.set>`. Remember to call :meth:`memoize
<.FanoutCache.memoize>` when decorating a callable. If you forget, then a
TypeError will occur::

    >>> @cache.memoize
    ... def test():
    ...     pass
    Traceback (most recent call last):
        ...
    TypeError: name cannot be callable

Observe the lack of parenthenses after :meth:`memoize
<diskcache.FanoutCache.memoize>` above.

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
            'TIMEOUT': 300,
            # ^-- Django setting for default timeout of each key.
            'SHARDS': 8,
            'DATABASE_TIMEOUT': 0.010,  # 10 milliseconds
            # ^-- Timeout for each DjangoCache database transaction.
            'OPTIONS': {
                'size_limit': 2 ** 30   # 1 gigabyte
            },
        },
    }

As with :class:`FanoutCache <diskcache.FanoutCache>` above, these settings
create a Django-compatible cache with eight shards and a 10ms timeout. You can
pass further settings via the ``OPTIONS`` mapping as shown in the Django
documentation. Only the ``BACKEND`` and ``LOCATION`` keys are necessary in the
above example. The other keys simply display their default
value. :class:`DjangoCache <diskcache.DjangoCache>` will never raise a
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
<diskcache.Deque>` objects use the :meth:`push <.Cache.push>`, :meth:`pull
<.Cache.pull>`, and :meth:`peek <.Cache.peek>` methods of :class:`Cache
<.Cache>` objects but never evict or expire items.

    >>> from diskcache import Deque
    >>> deque = Deque(range(5, 10))
    >>> deque.pop()
    9
    >>> deque.popleft()
    5
    >>> deque.appendleft('foo')
    >>> len(deque)
    4
    >>> type(deque.directory).__name__
    'str'
    >>> other = Deque(directory=deque.directory)
    >>> len(other)
    4
    >>> other.popleft()
    'foo'

:class:`Deque <diskcache.Deque>` objects provide an efficient and safe means of
cross-thread and cross-process communication. :class:`Deque <diskcache.Deque>`
objects are also useful in scenarios where contents should remain persistent or
limitations prohibit holding all items in memory at the same time. The deque
uses a fixed amout of memory regardless of the size or number of items stored
inside it.

Index
-----

:class:`diskcache.Index` uses a :class:`Cache <diskcache.Cache>` to provide a
`mutable mapping
<https://docs.python.org/3/library/collections.abc.html#collections-abstract-base-classes>`_
and `ordered dictionary
<https://docs.python.org/3/library/collections.html#collections.OrderedDict>`_
interface. :class:`Index <diskcache.Index>` objects inherit all the benefits of
:class:`Cache <diskcache.Cache>` objects but never evict or expire items.

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
limitations prohibit holding all items in memory at the same time. The index
uses a fixed amout of memory regardless of the size or number of items stored
inside it.

.. _tutorial-transactions:

Transactions
------------

Transactions are implemented by the :class:`.Cache`, :class:`.Deque`, and
:class:`.Index` data types and support consistency and improved
performance. Use transactions to guarantee a group of operations occur
atomically. For example, to calculate a running average, the total and count
could be incremented together::

    >>> with cache.transact():
    ...     total = cache.incr('total', 123.45)
    ...     count = cache.incr('count')
    >>> total
    123.45
    >>> count
    1

And to calculate the average, the values could be retrieved together:

    >>> with cache.transact():
    ...     total = cache.get('total')
    ...     count = cache.get('count')
    >>> average = None if count == 0 else total / count
    >>> average
    123.45

Keep transactions as short as possible because within a transaction, no other
writes may occur to the cache. Every write operation uses a transaction and
transactions may be nested to improve performance. For example, a possible
implementation to set many items within the cache::

    >>> def set_many(cache, mapping):
    ...     with cache.transact():
    ...         for key, value in mapping.items():
    ...             cache[key] = value

By grouping all operations in a single transaction, performance may improve two
to five times. But be careful, a large mapping will block other concurrent
writers.

Transactions are not implemented by :class:`.FanoutCache` and
:class:`.DjangoCache` due to key sharding. Instead, a cache shard with
transaction support may be requested.

    >>> fanout_cache = FanoutCache()
    >>> tutorial_cache = fanout_cache.cache('tutorial')
    >>> username_queue = fanout_cache.deque('usernames')
    >>> url_to_response = fanout_cache.index('responses')

The cache shard exists in a subdirectory of the fanout-cache with the given
name.

.. _tutorial-recipes:

Recipes
-------

:doc:`DiskCache <index>` includes a few synchronization recipes for
cross-thread and cross-process communication:

* :class:`.Averager` -- maintains a running average like that shown above.
* :class:`.Lock`, :class:`.RLock`, and :class:`.BoundedSemaphore` -- recipes
  for synchronization around critical sections like those found in Python's
  `threading`_ and `multiprocessing`_ modules.
* :func:`throttle <.throttle>` -- function decorator to rate-limit calls to a
  function.
* :func:`barrier <.barrier>` -- function decorator to synchronize calls to a
  function.
* :func:`memoize_stampede <.memoize_stampede>` -- memoizing function decorator
  with cache stampede protection. Read :doc:`case-study-landing-page-caching`
  for a comparison of memoization strategies.

.. _threading: https://docs.python.org/3/library/threading.html
.. _multiprocessing: https://docs.python.org/3/library/multiprocessing.html

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
  :meth:`cull <diskcache.Cache.cull>` in a separate process.
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

    >>> cache = Cache(size_limit=int(4e9))
    >>> print(cache.size_limit)
    4000000000
    >>> cache.disk_min_file_size
    32768
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

* `disk_min_file_size`, default 32 kilobytes. The minimum size to store a value
  in a file.
* `disk_pickle_protocol`, default highest Pickle protocol. The Pickle protocol
  to use for data types that are not natively supported.

An additional set of attributes correspond to SQLite pragmas. Changing these
values will also execute the appropriate ``PRAGMA`` statement. See the `SQLite
pragma documentation`_ for more details.

* `sqlite_auto_vacuum`, default 1, "FULL".
* `sqlite_cache_size`, default 8,192 pages.
* `sqlite_journal_mode`, default "wal".
* `sqlite_mmap_size`, default 64 megabytes.
* `sqlite_synchronous`, default 1, "NORMAL".

Each of these settings can passed to :class:`DjangoCache
<diskcache.DjangoCache>` via the ``OPTIONS`` key mapping. Always measure before
and after changing the default values. Default settings are programmatically
accessible at :data:`diskcache.DEFAULT_SETTINGS`.

.. _`SQLite pragma documentation`: https://www.sqlite.org/pragma.html

.. _tutorial-eviction-policies:

Eviction Policies
-----------------

:doc:`DiskCache <index>` supports four eviction policies each with different
tradeoffs for accessing and storing items.

* ``"least-recently-stored"`` is the default. Every cache item records the time
  it was stored in the cache. This policy adds an index to that field. On
  access, no update is required. Keys are evicted starting with the oldest
  stored keys. As :doc:`DiskCache <index>` was intended for large caches
  (gigabytes) this policy usually works well enough in practice.
* ``"least-recently-used"`` is the most commonly used policy. An index is added
  to the access time field stored in the cache database. On every access, the
  field is updated. This makes every access into a read and write which slows
  accesses.
* ``"least-frequently-used"`` works well in some cases. An index is added to
  the access count field stored in the cache database. On every access, the
  field is incremented. Every access therefore requires writing the database
  which slows accesses.
* ``"none"`` disables cache evictions. Caches will grow without bound. Cache
  items will still be lazily removed if they expire. The persistent data types,
  :class:`.Deque` and :class:`.Index`, use the ``"none"`` eviction policy. For
  :ref:`lazy culling <tutorial-culling>` use the :ref:`cull_limit <constants>`
  setting instead.

All clients accessing the cache are expected to use the same eviction
policy. The policy can be set during initialization using a keyword argument.

    >>> cache = Cache()
    >>> print(cache.eviction_policy)
    least-recently-stored
    >>> cache = Cache(eviction_policy='least-frequently-used')
    >>> print(cache.eviction_policy)
    least-frequently-used
    >>> print(cache.reset('eviction_policy', 'least-recently-used'))
    least-recently-used

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
example below uses compressed JSON, available for convenience as
:class:`JSONDisk <diskcache.JSONDisk>`.

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

    with Cache(disk=JSONDisk, disk_compress_level=6) as cache:
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

SQLite is used to synchronize database access between threads and processes and
as such inherits all SQLite caveats. Most notably SQLite is `not recommended`_
for use with Network File System (NFS) mounts. For this reason, :doc:`DiskCache
<index>` currently `performs poorly`_ on `Python Anywhere`_. Users have also
reported issues running inside of `Parallels`_ shared folders.

When the disk or database is full, a :exc:`sqlite3.OperationalError` will be
raised from any method that attempts to write data. Read operations will still
succeed so long as they do not cause any write (as might occur if cache
statistics are being recorded).

Asynchronous support using Python's ``async`` and ``await`` keywords and
`asyncio`_ module is blocked by a lack of support in the underlying SQLite
module. But it is possible to run :doc:`DiskCache <index>` methods in a
thread-pool executor asynchronously. For example::

    import asyncio

    async def set_async(key, val):
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(None, cache.set, key, val)
        result = await future
        return result

    asyncio.run(set_async('test-key', 'test-value'))

The cache :meth:`volume <diskcache.Cache.volume>` is based on the size of the
database that stores metadata and the size of the values stored in files. It
does not account the size of directories themselves or other filesystem
metadata. If directory count or size is a concern then consider implementing an
alternative :class:`Disk <diskcache.Disk>`.

.. _`hash protocol`: https://docs.python.org/library/functions.html#hash
.. _`not recommended`: https://www.sqlite.org/faq.html#q5
.. _`performs poorly`: https://www.pythonanywhere.com/forums/topic/1847/
.. _`Python Anywhere`: https://www.pythonanywhere.com/
.. _`Parallels`: https://www.parallels.com/
.. _`asyncio`: https://docs.python.org/3/library/asyncio.html

Implementation
--------------

:doc:`DiskCache <index>` is mostly built on SQLite and the filesystem. Some
techniques used to improve performance:

* Shard database to distribute writes.
* Leverage SQLite native types: integers, floats, unicode, and bytes.
* Use SQLite write-ahead-log so reads and writes don't block each other.
* Use SQLite memory-mapped pages to accelerate reads.
* Store small values in SQLite database and large values in files.
* Always use a SQLite index for queries.
* Use SQLite triggers to maintain key count and database size.

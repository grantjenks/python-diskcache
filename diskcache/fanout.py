"""Fanout cache automatically shards keys and values."""

import contextlib as cl
import functools
import itertools as it
import operator
import os
import os.path as op
import sqlite3
import tempfile
import threading
import time

from .core import (
    DEFAULT_SETTINGS,
    ENOVAL,
    Cache,
    Disk,
    Timeout,
    _emit_pickle_key_warning,
    _PICKLE_KEY_UNSET,
    _resolve_pickle_key_for_directory,
)
from .persistent import Deque, Index


class FanoutCache:
    """Cache that shards keys and values."""

    def __init__(
        self, directory=None, shards=8, timeout=0.010, disk=Disk, **settings
    ):
        """Initialize cache instance.

        :param str directory: cache directory
        :param int shards: number of shards to distribute writes
        :param float timeout: SQLite connection timeout
        :param disk: `Disk` instance for serialization
        :param settings: any of `DEFAULT_SETTINGS`, plus the optional
            non-persistent ``disk_pickle_key`` argument used to verify
            pickle envelopes (CVE-2025-69872).  See
            :class:`diskcache.Disk` for accepted values.  The key is
            resolved once at the FanoutCache root and forwarded to all
            shards so sharding stays deterministic across processes
            and a single warning is emitted in default mode.

        """
        if directory is None:
            directory = tempfile.mkdtemp(prefix='diskcache-')
        directory = str(directory)
        directory = op.expanduser(directory)
        directory = op.expandvars(directory)

        default_size_limit = DEFAULT_SETTINGS['size_limit']
        size_limit = settings.pop('size_limit', default_size_limit) / shards

        # CVE-2025-69872: resolve the pickle HMAC key once at the
        # FanoutCache root.  Without this, each shard would
        # independently auto-generate its own ``.diskcache_pickle_key``
        # file -- making sharding non-deterministic across processes
        # (FanoutCache._hash uses shard 0's key but storage may land in
        # shard N which holds a different key) and emitting one
        # warning per shard.
        # CVE-2025-69872 (V5): skip eager key resolution for Disk
        # subclasses that never use pickle (e.g. JSONDisk).  Without
        # this we would auto-generate ``.diskcache_pickle_key`` and
        # emit an UnsafePickleWarning even though the cache will never
        # exercise the pickle path.
        pickle_key_arg = settings.pop('disk_pickle_key', _PICKLE_KEY_UNSET)
        # CVE-2025-69872 (O1+O4 link): private inherited-key channel
        # used by ``_copy_for_same_process`` (and by Cache children
        # constructed under another FanoutCache).  When set we skip
        # env/file resolution, skip the warning (the upstream context
        # already warned), and leave ``_pickle_key_user_arg`` UNSET so
        # the FanoutCache stays pickleable in default mode.
        inherited_key = settings.pop('_disk_pickle_key_inherited', None)
        # V1: remember the user's original argument so __getstate__
        # only refuses pickling when the user explicitly provided a
        # secret.  Auto-generated / env-var keys can be re-resolved in
        # the receiving process, so default-mode FanoutCache pickling
        # remains supported.
        self._pickle_key_user_arg = pickle_key_arg
        # CVE-2025-69872 (Y3): pre-validate the user-explicit key with
        # the public kwarg name in the error message.
        if (
            pickle_key_arg is not _PICKLE_KEY_UNSET
            and pickle_key_arg is not None
            and pickle_key_arg is not False
        ):
            from .core import _coerce_pickle_key

            pickle_key_arg = _coerce_pickle_key(
                pickle_key_arg, source='disk_pickle_key argument'
            )
        if inherited_key is not None and pickle_key_arg is _PICKLE_KEY_UNSET:
            # Use the inherited key directly; do NOT resolve from env
            # or file and do NOT warn -- the parent context already
            # handled both.
            resolved_key = inherited_key
        elif getattr(disk, '_uses_pickle', True):
            if not op.isdir(directory):
                os.makedirs(directory, 0o755, exist_ok=True)
            resolved_key, source = _resolve_pickle_key_for_directory(
                directory, pickle_key_arg
            )
            _emit_pickle_key_warning(source, directory, stacklevel=3)
        else:
            # Forward the user's explicit choice unchanged so that any
            # custom Disk subclass that mixes pickle + non-pickle paths
            # still honours an explicit key.  No file/env resolution.
            resolved_key = pickle_key_arg

        self._count = shards
        self._directory = directory
        self._disk = disk
        shard_kwargs = dict(settings)
        if pickle_key_arg is not _PICKLE_KEY_UNSET and pickle_key_arg is not None:
            # User-explicit (bytes / False): forward as the public
            # kwarg so the shard's ``_pickle_key_arg`` reflects the
            # explicit choice (and __getstate__ refuses pickling).
            shard_kwargs['disk_pickle_key'] = (
                resolved_key if resolved_key is not _PICKLE_KEY_UNSET
                else pickle_key_arg
            )
        elif (
            resolved_key is not _PICKLE_KEY_UNSET
            and resolved_key is not False
            and resolved_key is not None
        ):
            # Default / env / file: forward via the inherited channel
            # so each shard uses the same bytes without claiming to be
            # user-explicit (default-mode pickling remains allowed).
            shard_kwargs['_disk_pickle_key_inherited'] = resolved_key
        self._shards = tuple(
            Cache(
                directory=op.join(directory, '%03d' % num),
                timeout=timeout,
                disk=disk,
                size_limit=size_limit,
                **shard_kwargs,
            )
            for num in range(shards)
        )
        # Suppress per-shard warnings: the FanoutCache already emitted
        # one above for the entire ensemble (when applicable).
        for shard in self._shards:
            shard._disk._pickle_key_warned = True
        self._hash = self._shards[0].disk.hash
        self._caches = {}
        self._deques = {}
        self._indexes = {}
        # CVE-2025-69872 (O2): serialize child get-or-create so two
        # concurrent ``cache('foo')`` / ``deque('foo')`` / ``index('foo')``
        # calls cannot construct two Cache instances on the same
        # SQLite database (which would race on initial schema setup
        # and hold separate connection pools).
        self._children_lock = threading.Lock()
        # CVE-2025-69872 (C1): track close state so cache()/deque()/
        # index() refuse to construct NEW children after close().
        # Existing child references obtained before close() remain
        # usable per :meth:`Cache.close` semantics (per-thread
        # connection that lazily reopens).
        self._closed = False

    @property
    def directory(self):
        """Cache directory."""
        return self._directory

    def __getattr__(self, name):
        safe_names = {'timeout', 'disk'}
        valid_name = name in DEFAULT_SETTINGS or name in safe_names
        assert valid_name, 'cannot access {} in cache shard'.format(name)
        return getattr(self._shards[0], name)

    @cl.contextmanager
    def transact(self, retry=True):
        """Context manager to perform a transaction by locking the cache.

        While the cache is locked, no other write operation is permitted.
        Transactions should therefore be as short as possible. Read and write
        operations performed in a transaction are atomic. Read operations may
        occur concurrent to a transaction.

        Transactions may be nested and may not be shared between threads.

        Blocks until transactions are held on all cache shards by retrying as
        necessary.

        >>> cache = FanoutCache()
        >>> with cache.transact():  # Atomically increment two keys.
        ...     _ = cache.incr('total', 123.4)
        ...     _ = cache.incr('count', 1)
        >>> with cache.transact():  # Atomically calculate average.
        ...     average = cache['total'] / cache['count']
        >>> average
        123.4

        :return: context manager for use in `with` statement

        """
        assert retry, 'retry must be True in FanoutCache'
        with cl.ExitStack() as stack:
            for shard in self._shards:
                shard_transaction = shard.transact(retry=True)
                stack.enter_context(shard_transaction)
            yield

    def set(self, key, value, expire=None, read=False, tag=None, retry=False):
        """Set `key` and `value` item in cache.

        When `read` is `True`, `value` should be a file-like object opened
        for reading in binary mode.

        If database timeout occurs then fails silently unless `retry` is set to
        `True` (default `False`).

        :param key: key for item
        :param value: value for item
        :param float expire: seconds until the key expires
            (default None, no expiry)
        :param bool read: read value as raw bytes from file (default False)
        :param str tag: text to associate with key (default None)
        :param bool retry: retry if database timeout occurs (default False)
        :return: True if item was set

        """
        index = self._hash(key) % self._count
        shard = self._shards[index]
        try:
            return shard.set(key, value, expire, read, tag, retry)
        except Timeout:
            return False

    def __setitem__(self, key, value):
        """Set `key` and `value` item in cache.

        Calls :func:`FanoutCache.set` internally with `retry` set to `True`.

        :param key: key for item
        :param value: value for item

        """
        index = self._hash(key) % self._count
        shard = self._shards[index]
        shard[key] = value

    def touch(self, key, expire=None, retry=False):
        """Touch `key` in cache and update `expire` time.

        If database timeout occurs then fails silently unless `retry` is set to
        `True` (default `False`).

        :param key: key for item
        :param float expire: seconds until the key expires
            (default None, no expiry)
        :param bool retry: retry if database timeout occurs (default False)
        :return: True if key was touched

        """
        index = self._hash(key) % self._count
        shard = self._shards[index]
        try:
            return shard.touch(key, expire, retry)
        except Timeout:
            return False

    def add(self, key, value, expire=None, read=False, tag=None, retry=False):
        """Add `key` and `value` item to cache.

        Similar to `set`, but only add to cache if key not present.

        This operation is atomic. Only one concurrent add operation for given
        key from separate threads or processes will succeed.

        When `read` is `True`, `value` should be a file-like object opened
        for reading in binary mode.

        If database timeout occurs then fails silently unless `retry` is set to
        `True` (default `False`).

        :param key: key for item
        :param value: value for item
        :param float expire: seconds until the key expires
            (default None, no expiry)
        :param bool read: read value as bytes from file (default False)
        :param str tag: text to associate with key (default None)
        :param bool retry: retry if database timeout occurs (default False)
        :return: True if item was added

        """
        index = self._hash(key) % self._count
        shard = self._shards[index]
        try:
            return shard.add(key, value, expire, read, tag, retry)
        except Timeout:
            return False

    def incr(self, key, delta=1, default=0, retry=False):
        """Increment value by delta for item with key.

        If key is missing and default is None then raise KeyError. Else if key
        is missing and default is not None then use default for value.

        Operation is atomic. All concurrent increment operations will be
        counted individually.

        Assumes value may be stored in a SQLite column. Most builds that target
        machines with 64-bit pointer widths will support 64-bit signed
        integers.

        If database timeout occurs then fails silently unless `retry` is set to
        `True` (default `False`).

        :param key: key for item
        :param int delta: amount to increment (default 1)
        :param int default: value if key is missing (default 0)
        :param bool retry: retry if database timeout occurs (default False)
        :return: new value for item on success else None
        :raises KeyError: if key is not found and default is None

        """
        index = self._hash(key) % self._count
        shard = self._shards[index]
        try:
            return shard.incr(key, delta, default, retry)
        except Timeout:
            return None

    def decr(self, key, delta=1, default=0, retry=False):
        """Decrement value by delta for item with key.

        If key is missing and default is None then raise KeyError. Else if key
        is missing and default is not None then use default for value.

        Operation is atomic. All concurrent decrement operations will be
        counted individually.

        Unlike Memcached, negative values are supported. Value may be
        decremented below zero.

        Assumes value may be stored in a SQLite column. Most builds that target
        machines with 64-bit pointer widths will support 64-bit signed
        integers.

        If database timeout occurs then fails silently unless `retry` is set to
        `True` (default `False`).

        :param key: key for item
        :param int delta: amount to decrement (default 1)
        :param int default: value if key is missing (default 0)
        :param bool retry: retry if database timeout occurs (default False)
        :return: new value for item on success else None
        :raises KeyError: if key is not found and default is None

        """
        index = self._hash(key) % self._count
        shard = self._shards[index]
        try:
            return shard.decr(key, delta, default, retry)
        except Timeout:
            return None

    def get(
        self,
        key,
        default=None,
        read=False,
        expire_time=False,
        tag=False,
        retry=False,
    ):
        """Retrieve value from cache. If `key` is missing, return `default`.

        If database timeout occurs then returns `default` unless `retry` is set
        to `True` (default `False`).

        :param key: key for item
        :param default: return value if key is missing (default None)
        :param bool read: if True, return file handle to value
            (default False)
        :param float expire_time: if True, return expire_time in tuple
            (default False)
        :param tag: if True, return tag in tuple (default False)
        :param bool retry: retry if database timeout occurs (default False)
        :return: value for item if key is found else default

        """
        index = self._hash(key) % self._count
        shard = self._shards[index]
        try:
            return shard.get(key, default, read, expire_time, tag, retry)
        except (Timeout, sqlite3.OperationalError):
            return default

    def __getitem__(self, key):
        """Return corresponding value for `key` from cache.

        Calls :func:`FanoutCache.get` internally with `retry` set to `True`.

        :param key: key for item
        :return: value for item
        :raises KeyError: if key is not found

        """
        index = self._hash(key) % self._count
        shard = self._shards[index]
        return shard[key]

    def read(self, key):
        """Return file handle corresponding to `key` from cache.

        :param key: key for item
        :return: file open for reading in binary mode
        :raises KeyError: if key is not found

        """
        handle = self.get(key, default=ENOVAL, read=True, retry=True)
        if handle is ENOVAL:
            raise KeyError(key)
        return handle

    def __contains__(self, key):
        """Return `True` if `key` matching item is found in cache.

        :param key: key for item
        :return: True if key is found

        """
        index = self._hash(key) % self._count
        shard = self._shards[index]
        return key in shard

    def pop(
        self, key, default=None, expire_time=False, tag=False, retry=False
    ):  # noqa: E501
        """Remove corresponding item for `key` from cache and return value.

        If `key` is missing, return `default`.

        Operation is atomic. Concurrent operations will be serialized.

        If database timeout occurs then fails silently unless `retry` is set to
        `True` (default `False`).

        :param key: key for item
        :param default: return value if key is missing (default None)
        :param float expire_time: if True, return expire_time in tuple
            (default False)
        :param tag: if True, return tag in tuple (default False)
        :param bool retry: retry if database timeout occurs (default False)
        :return: value for item if key is found else default

        """
        index = self._hash(key) % self._count
        shard = self._shards[index]
        try:
            return shard.pop(key, default, expire_time, tag, retry)
        except Timeout:
            return default

    def delete(self, key, retry=False):
        """Delete corresponding item for `key` from cache.

        Missing keys are ignored.

        If database timeout occurs then fails silently unless `retry` is set to
        `True` (default `False`).

        :param key: key for item
        :param bool retry: retry if database timeout occurs (default False)
        :return: True if item was deleted

        """
        index = self._hash(key) % self._count
        shard = self._shards[index]
        try:
            return shard.delete(key, retry)
        except Timeout:
            return False

    def __delitem__(self, key):
        """Delete corresponding item for `key` from cache.

        Calls :func:`FanoutCache.delete` internally with `retry` set to `True`.

        :param key: key for item
        :raises KeyError: if key is not found

        """
        index = self._hash(key) % self._count
        shard = self._shards[index]
        del shard[key]

    def check(self, fix=False, retry=False):
        """Check database and file system consistency.

        Intended for use in testing and post-mortem error analysis.

        While checking the cache table for consistency, a writer lock is held
        on the database. The lock blocks other cache clients from writing to
        the database. For caches with many file references, the lock may be
        held for a long time. For example, local benchmarking shows that a
        cache with 1,000 file references takes ~60ms to check.

        If database timeout occurs then fails silently unless `retry` is set to
        `True` (default `False`).

        :param bool fix: correct inconsistencies
        :param bool retry: retry if database timeout occurs (default False)
        :return: list of warnings
        :raises Timeout: if database timeout occurs

        """
        warnings = (shard.check(fix, retry) for shard in self._shards)
        return functools.reduce(operator.iadd, warnings, [])

    def expire(self, retry=False):
        """Remove expired items from cache.

        If database timeout occurs then fails silently unless `retry` is set to
        `True` (default `False`).

        :param bool retry: retry if database timeout occurs (default False)
        :return: count of items removed

        """
        return self._remove('expire', args=(time.time(),), retry=retry)

    def create_tag_index(self):
        """Create tag index on cache database.

        Better to initialize cache with `tag_index=True` than use this.

        :raises Timeout: if database timeout occurs

        """
        for shard in self._shards:
            shard.create_tag_index()

    def drop_tag_index(self):
        """Drop tag index on cache database.

        :raises Timeout: if database timeout occurs

        """
        for shard in self._shards:
            shard.drop_tag_index()

    def evict(self, tag, retry=False):
        """Remove items with matching `tag` from cache.

        If database timeout occurs then fails silently unless `retry` is set to
        `True` (default `False`).

        :param str tag: tag identifying items
        :param bool retry: retry if database timeout occurs (default False)
        :return: count of items removed

        """
        return self._remove('evict', args=(tag,), retry=retry)

    def cull(self, retry=False):
        """Cull items from cache until volume is less than size limit.

        If database timeout occurs then fails silently unless `retry` is set to
        `True` (default `False`).

        :param bool retry: retry if database timeout occurs (default False)
        :return: count of items removed

        """
        return self._remove('cull', retry=retry)

    def clear(self, retry=False):
        """Remove all items from cache.

        If database timeout occurs then fails silently unless `retry` is set to
        `True` (default `False`).

        :param bool retry: retry if database timeout occurs (default False)
        :return: count of items removed

        """
        return self._remove('clear', retry=retry)

    def _remove(self, name, args=(), retry=False):
        total = 0
        for shard in self._shards:
            method = getattr(shard, name)
            while True:
                try:
                    count = method(*args, retry=retry)
                    total += count
                except Timeout as timeout:
                    total += timeout.args[0]
                else:
                    break
        return total

    def stats(self, enable=True, reset=False):
        """Return cache statistics hits and misses.

        :param bool enable: enable collecting statistics (default True)
        :param bool reset: reset hits and misses to 0 (default False)
        :return: (hits, misses)

        """
        results = [shard.stats(enable, reset) for shard in self._shards]
        total_hits = sum(hits for hits, _ in results)
        total_misses = sum(misses for _, misses in results)
        return total_hits, total_misses

    def volume(self):
        """Return estimated total size of cache on disk.

        :return: size in bytes

        """
        return sum(shard.volume() for shard in self._shards)

    def close(self):
        """Close database connection."""
        # CVE-2025-69872 (O3): close cached child Cache/Deque/Index
        # instances BEFORE the shards so their SQLite connections
        # release file handles cleanly (otherwise long-lived
        # references via ``fc.cache('foo')`` keep their connections
        # open after ``fc.close()``, leaking handles and quietly
        # accepting writes against a "closed" FanoutCache).
        with self._children_lock:
            # CVE-2025-69872 (C1): mark closed under the lock so any
            # concurrent cache()/deque()/index() either completes
            # before us (returning a still-valid child we then close)
            # or sees ``_closed`` True and refuses cleanly.
            self._closed = True
            for child in list(self._caches.values()):
                with cl.suppress(Exception):
                    child.close()
            for child in list(self._deques.values()):
                with cl.suppress(Exception):
                    child._cache.close()
            for child in list(self._indexes.values()):
                with cl.suppress(Exception):
                    child._cache.close()
            self._caches.clear()
            self._deques.clear()
            self._indexes.clear()
        for shard in self._shards:
            shard.close()

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()

    def __getstate__(self):
        # CVE-2025-69872 (V1): mirror :meth:`Cache.__getstate__`'s
        # protection.  Only refuse when the *user* supplied an
        # explicit secret (or False) -- auto-generated / env-var keys
        # are re-resolved by the receiving process, so default-mode
        # pickling still works.
        arg = self._pickle_key_user_arg
        if arg is not _PICKLE_KEY_UNSET and arg is not None:
            raise TypeError(
                'diskcache: FanoutCache instances configured with an '
                'explicit disk_pickle_key (or disk_pickle_key=False) '
                'cannot be pickled because the secret is not placed '
                'in pickle state. Pickle the cache directory path '
                'instead and reconstruct FanoutCache(directory, '
                'disk_pickle_key=...) in the receiving process. '
                '(CVE-2025-69872)'
            )
        return (self._directory, self._count, self.timeout, type(self.disk))

    def __setstate__(self, state):
        self.__init__(*state)

    def __iter__(self):
        """Iterate keys in cache including expired items."""
        iterators = (iter(shard) for shard in self._shards)
        return it.chain.from_iterable(iterators)

    def __reversed__(self):
        """Reverse iterate keys in cache including expired items."""
        iterators = (reversed(shard) for shard in reversed(self._shards))
        return it.chain.from_iterable(iterators)

    def __len__(self):
        """Count of items in cache including expired items."""
        return sum(len(shard) for shard in self._shards)

    def reset(self, key, value=ENOVAL):
        """Reset `key` and `value` item from Settings table.

        If `value` is not given, it is reloaded from the Settings
        table. Otherwise, the Settings table is updated.

        Settings attributes on cache objects are lazy-loaded and
        read-only. Use `reset` to update the value.

        Settings with the ``sqlite_`` prefix correspond to SQLite
        pragmas. Updating the value will execute the corresponding PRAGMA
        statement.

        :param str key: Settings key for item
        :param value: value for item (optional)
        :return: updated value for item

        """
        for shard in self._shards:
            while True:
                try:
                    result = shard.reset(key, value)
                except Timeout:
                    pass
                else:
                    break
        return result

    def cache(self, name, timeout=60, disk=None, **settings):
        """Return Cache with given `name` in subdirectory.

        If disk is none (default), uses the fanout cache disk.

        >>> fanout_cache = FanoutCache()
        >>> cache = fanout_cache.cache('test')
        >>> cache.set('abc', 123)
        True
        >>> cache.get('abc')
        123
        >>> len(cache)
        1
        >>> cache.delete('abc')
        True

        :param str name: subdirectory name for Cache
        :param float timeout: SQLite connection timeout
        :param disk: Disk type or subclass for serialization
        :param settings: any of DEFAULT_SETTINGS
        :return: Cache with given name

        """
        # CVE-2025-69872 (O2): double-checked-locking get-or-create.
        with self._children_lock:
            if self._closed:
                raise RuntimeError(
                    'diskcache: FanoutCache is closed; cannot create '
                    'new children. (Existing child references obtained '
                    'before close() remain usable per Cache.close() '
                    'semantics.)'
                )
            existing = self._caches.get(name)
            if existing is not None:
                return existing
            parts = name.split('/')
            directory = op.join(self._directory, 'cache', *parts)
            # CVE-2025-69872 V16/O4: forward the FanoutCache's resolved
            # pickle key to the child cache so it doesn't auto-
            # generate its own (different) ``.diskcache_pickle_key``
            # under the child directory.  Caller-supplied settings
            # win on conflict.
            self._inject_disk_pickle_key(settings)
            temp = Cache(
                directory=directory,
                timeout=timeout,
                disk=self._disk if disk is None else Disk,
                **settings,
            )
            self._caches[name] = temp
            return temp

    def deque(self, name, maxlen=None):
        """Return Deque with given `name` in subdirectory.

        >>> cache = FanoutCache()
        >>> deque = cache.deque('test')
        >>> deque.extend('abc')
        >>> deque.popleft()
        'a'
        >>> deque.pop()
        'c'
        >>> len(deque)
        1

        :param str name: subdirectory name for Deque
        :param maxlen: max length (default None, no max)
        :return: Deque with given name

        """
        with self._children_lock:
            if self._closed:
                raise RuntimeError(
                    'diskcache: FanoutCache is closed; cannot create '
                    'new children.'
                )
            existing = self._deques.get(name)
            if existing is not None:
                return existing
            parts = name.split('/')
            directory = op.join(self._directory, 'deque', *parts)
            child_kwargs = {}
            self._inject_disk_pickle_key(child_kwargs)
            cache = Cache(
                directory=directory,
                disk=self._disk,
                eviction_policy='none',
                **child_kwargs,
            )
            deque = Deque.fromcache(cache, maxlen=maxlen)
            self._deques[name] = deque
            return deque

    def index(self, name):
        """Return Index with given `name` in subdirectory.

        >>> cache = FanoutCache()
        >>> index = cache.index('test')
        >>> index['abc'] = 123
        >>> index['def'] = 456
        >>> index['ghi'] = 789
        >>> index.popitem()
        ('ghi', 789)
        >>> del index['abc']
        >>> len(index)
        1
        >>> index['def']
        456

        :param str name: subdirectory name for Index
        :return: Index with given name

        """
        with self._children_lock:
            if self._closed:
                raise RuntimeError(
                    'diskcache: FanoutCache is closed; cannot create '
                    'new children.'
                )
            existing = self._indexes.get(name)
            if existing is not None:
                return existing
            parts = name.split('/')
            directory = op.join(self._directory, 'index', *parts)
            child_kwargs = {}
            self._inject_disk_pickle_key(child_kwargs)
            cache = Cache(
                directory=directory,
                disk=self._disk,
                eviction_policy='none',
                **child_kwargs,
            )
            index = Index.fromcache(cache)
            self._indexes[name] = index
            return index

    def _inject_disk_pickle_key(self, kwargs):
        """CVE-2025-69872 V16/O4 helper: forward the FanoutCache's
        resolved pickle key to a child Cache constructor's kwargs so
        the child does not run an independent default-fallback
        resolution (which would create a separate
        ``.diskcache_pickle_key`` file under the child directory and,
        critically, would use a *different* HMAC key than the parent
        and its sibling shards).

        Default-mode keys are forwarded via ``_disk_pickle_key_inherited``
        so the child's ``_pickle_key_arg`` stays UNSET -- otherwise
        ``Cache.__getstate__`` would refuse to pickle a default-mode
        child (the resolved key isn't a user-supplied secret, just an
        env/file value the child can't decide for itself).
        """
        if (
            'disk_pickle_key' in kwargs
            or '_disk_pickle_key_inherited' in kwargs
        ):
            return  # caller-supplied wins
        # User-explicit (bytes / False): forward as the public kwarg
        # so the child's __getstate__ refuses pickling, matching the
        # parent's posture.
        arg = self._pickle_key_user_arg
        if arg is not _PICKLE_KEY_UNSET and arg is not None:
            kwargs['disk_pickle_key'] = arg
            return
        # Default mode: forward the already-resolved bytes via the
        # inherited channel so the child remains pickleable but uses
        # the same key as the parent and its sibling shards.
        if self._shards:
            shard_disk = self._shards[0]._disk
            shard_arg = shard_disk._pickle_key_arg
            if shard_arg is not _PICKLE_KEY_UNSET and shard_arg is not None:
                kwargs['disk_pickle_key'] = shard_arg
                return
            resolved = getattr(shard_disk, '_pickle_key_resolved', None)
            if resolved is not None and resolved is not False:
                kwargs['_disk_pickle_key_inherited'] = resolved

    def __copy__(self):
        return self._copy_for_same_process()

    def __deepcopy__(self, memo):
        return self._copy_for_same_process()

    def _copy_for_same_process(self):
        # CVE-2025-69872 V19/O1: same-process copy preserves the
        # user's explicit pickle_key (or False) so a copied
        # FanoutCache stays in the same security mode as the
        # original.  Default-mode FanoutCaches forward the already-
        # resolved key via the inherited channel so an intervening
        # change to ``DISKCACHE_PICKLE_KEY`` or
        # ``.diskcache_pickle_key`` does NOT produce a copy that
        # uses a different key (which would silently fail HMAC
        # verification on shared data).
        kwargs = {}
        arg = self._pickle_key_user_arg
        if arg is not _PICKLE_KEY_UNSET:
            kwargs['disk_pickle_key'] = arg
        elif self._shards:
            shard_disk = self._shards[0]._disk
            resolved = getattr(shard_disk, '_pickle_key_resolved', None)
            if resolved is not None and resolved is not False:
                kwargs['_disk_pickle_key_inherited'] = resolved
        return self.__class__(
            self._directory,
            shards=self._count,
            timeout=self.timeout,
            disk=self._disk,
            **kwargs,
        )


FanoutCache.memoize = Cache.memoize  # type: ignore

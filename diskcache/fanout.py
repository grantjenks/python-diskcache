"Fanout cache automatically shards keys and values."

import sqlite3

from .core import Cache, Disk, ENOVAL

class FanoutCache(object):
    "Cache that shards keys and values."
    def __init__(self, directory, shards=8, timeout=0.025, disk=Disk(),
                 **settings):
        """Initialize FanoutCache instance.

        :param str directory: cache directory
        :param int shards: number of shards to distribute writes
        :param float timeout: SQLite connection timeout
        :param disk: `Disk` instance for serialization
        :param settings: any of `DEFAULT_SETTINGS`

        """
        object.__setattr__(self, '_count', shards)

        object.__setattr__(self, '_shards', tuple(
            Cache(
                '%s/%03d' % (directory, num),
                timeout=timeout,
                disk=disk,
                **settings
            )
            for num in range(shards)
        ))


    def __getattr__(self, name):
        return getattr(self._shards[0], name)


    def __setattr__(self, name, value):
        for shard in self._shards:
            setattr(shard, name, value)


    def set(self, key, value, expire=None, read=False, tag=None):
        """Set key, value pair in cache.

        When `read` is `True`, `value` should be a file-like object opened
        for reading in binary mode.

        :param key: Python key to store
        :param value: Python value to store
        :param expire: seconds until the key expires (default None, no expiry)
        :param bool read: read value as raw bytes from file (default False)
        :param tag: text to associate with key (default None)
        :return: True if item was successfully set

        """
        try:
            index = hash(key) % self._count
            return self._shards[index].set(
                key, value, expire=expire, read=read, tag=tag,
            )
        except sqlite3.OperationalError:
            return False


    __setitem__ = set


    def add(self, key, value, expire=None, read=False, tag=None):
        """Add key, value pair to cache.

        Similar to `set`, but only set in cache if key not present.

        This operation is atomic. Only one concurrent add operation for given
        key from separate threads or processes will succeed.

        When `read` is `True`, `value` should be a file-like object opened
        for reading in binary mode.

        :param key: Python key to store
        :param value: Python value to store
        :param float expire: seconds until the key expires
            (default None, no expiry)
        :param bool read: read value as bytes from file (default False)
        :param str tag: text to associate with key (default None)
        :return: True if item was successfully added

        """
        try:
            index = hash(key) % self._count
            return self._shards[index].add(
                key, value, expire=expire, read=read, tag=tag,
            )
        except sqlite3.OperationalError:
            return False


    def get(self, key, default=None, read=False, expire_time=False, tag=False):
        """Retrieve value from cache. If key is missing, return default.

        :param key: Python key to retrieve
        :param default: value to return if key is missing (default None)
        :param bool read: if True, return file handle to value
            (default False)
        :param float expire_time: if True, return expire_time in tuple
            (default False)
        :param tag: if True, return tag in tuple (default False)
        :return: corresponding value or `default` if not found

        """
        try:
            index = hash(key) % self._count
            return self._shards[index].get(
                key,
                default=default, read=read, expire_time=expire_time, tag=tag,
            )
        except sqlite3.OperationalError:
            return default


    def __getitem__(self, key):
        "Return corresponding value for `key` from Cache."
        value = self.get(key, default=ENOVAL)
        if value is ENOVAL:
            raise KeyError(key)
        return value


    def read(self, key):
        """Return file handle corresponding to `key` from Cache.

        :param key: Python key to retrieve
        :return: file open for reading in binary mode
        :raises KeyError: if key is not found

        """
        handle = self.get(key, default=ENOVAL, read=True)
        if handle is ENOVAL:
            raise KeyError(key)
        return handle


    def __contains__(self, key):
        "Return True if `key` in Cache."
        try:
            index = hash(key) % self._count
            return key in self._shards[index]
        except sqlite3.OperationalError:
            return False


    def __delitem__(self, key):
        "Delete corresponding item for `key` from Cache."
        try:
            index = hash(key) % self._count
            return self._shards[index].__delitem__(key)
        except sqlite3.OperationalError:
            return False


    def delete(self, key):
        """Delete corresponding item for `key` from Cache.

        Missing keys are ignored.

        """
        try:
            return self.__delitem__(key)
        except KeyError:
            return False


    def check(self, fix=False):
        """Check database and file system consistency.

        :param bool fix: fix inconsistencies
        :return: list of warnings

        """
        return sum((shard.check(fix=fix) for shard in self._shards), [])


    def expire(self):
        "Remove expired items from Cache."
        return sum(shard.expire() for shard in self._shards)


    def evict(self, tag):
        "Remove items with matching `tag` from Cache."
        return sum(shard.evict(tag) for shard in self._shards)


    def clear(self):
        "Remove all items from Cache."
        return sum(shard.clear() for shard in self._shards)


    def stats(self, enable=True, reset=False):
        """Return cache statistics pair: (hits, misses).

        :param bool enable: enable collecting statistics (default True)
        :param bool reset: reset hits and misses to 0 (default False)
        :return: (hits, misses)

        """
        results = [shard.stats(enable, reset) for shard in self._shards]
        return (sum(result[0] for result in results),
                sum(result[1] for result in results))


    def volume(self):
        """Return estimated total size of cache on disk.

        :return: size in bytes

        """
        return sum(shard.volume() for shard in self._shards)


    def close(self):
        "Close database connection."
        for shard in self._shards:
            shard.close()


    def __enter__(self):
        return self


    def __exit__(self, *exception):
        self.close()


    def __len__(self):
        return sum(len(shard) for shard in self._shards)

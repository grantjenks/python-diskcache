"Fanout cache automatically shards keys and values."

import sqlite3

from .core import Cache, Disk, ENOVAL

class FanoutCache(object):
    "Cache that shards keys and values."
    def __init__(self, directory, shards=15, timeout=0.025, disk=Disk(),
                 **settings):

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


    def set(self, key, value, read=False, expire=None, tag=None):
        """Store key, value pair in cache.

        When `read` is `True`, `value` should be a file-like object opened
        for reading in binary mode.

        Keyword arguments:
        expire -- seconds until the key expires (default None, no expiry)
        tag -- text to associate with key (default None)
        read -- read value as raw bytes from file (default False)

        """
        try:
            index = hash(key) % self._count
            return self._shards[index].set(
                key, value, read=read, expire=expire, tag=tag,
            )
        except sqlite3.OperationalError:
            return False

    __setitem__ = set


    def get(self, key, default=None, read=False, expire_time=False, tag=False):
        """Get key from cache. If key is missing, return default.

        Keyword arguments:
        default -- value to return if key is missing (default None)
        read -- if True, return open file handle to value (default False)
        expire_time -- if True, return expire_time in tuple (default False)
        tag -- if True, return tag in tuple (default False)

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
        value = self.get(key, default=ENOVAL)
        if value is ENOVAL:
            raise KeyError(key)
        return value


    def __contains__(self, key):
        try:
            index = hash(key) % self._count
            return key in self._shards[index]
        except sqlite3.OperationalError:
            return False


    def __delitem__(self, key):
        try:
            index = hash(key) % self._count
            return self._shards[index].__delitem__(key)
        except sqlite3.OperationalError:
            return False


    def delete(self, key):
        "Delete key from cache. Missing keys are ignored."
        try:
            return self.__delitem__(key)
        except KeyError:
            return False


    def check(self):
        "Check database and file system consistency."
        return sum(shard.check() for shard in self._shards)


    def expire(self):
        "Remove expired items from Cache."
        return sum(shard.expire() for shard in self._shards)


    def evict(self, tag):
        "Remove items with matching tag from Cache."
        return sum(shard.evict(tag) for shard in self._shards)


    def clear(self):
        "Remove all items from Cache."
        return sum(shard.clear() for shard in self._shards)


    def stats(self, enable=True, reset=False):
        """Return cache statistics pair: hits, misses.

        Keyword arguments:
        enable -- enable collecting statistics (default True)
        reset -- reset hits and misses to 0 (default False)

        """
        results = [shard.stats(enable, reset) for shard in self._shards]
        return (sum(result[0] for result in results),
                sum(result[1] for result in results))


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

"Fanout cache automatically shards keys and values."

import sqlite3

from .core import Cache, Disk

class FanoutCache(object):
    "Cache that shards keys and values."
    def __init__(self, directory, shards=2, timeout=1, disk=Disk(),
                 **settings):

        self._count = shards

        self._shards = [
            Cache(
                '%s/%03d' % (directory, num),
                timeout=timeout,
                disk=Disk(),
                **settings
            )
            for num in range(shards)
        ]


    def set(self, key, value, read=False, expire=None, tag=None):
        try:
            index = hash(key) % self._count
            return self._shards[index].set(
                key, value, read=read, expire=expire, tag=tag,
            )
        except sqlite3.OperationalError:
            return False
    
    __setitem__ = set


    def get(self, key, default=None, read=False, expire_time=False, tag=False):
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
            del self._shards[index][key]
        except sqlite3.OperationalError:
            return False


    def delete(self, key):
        "Delete key from cache. Missing keys are ignored."
        try:
            return self.__delitem__(key)
        except KeyError:
            return False


    def check(self):
        return sum(shard.check() for shard in self._shards)


    def expire(self):
        return sum(shard.expire() for shard in self._shards)


    def evict(self, tag):
        return sum(shard.evict(tag) for shard in self._shards)


    def clear(self):
        return sum(shard.clear() for shard in self._shards)


    def stats(self, enable=True, reset=False):
        results = [shard.stats(enable, reset) for shard in self._shards]
        return (sum(results[0]), sum(results[1]))


    def close(self):
        for shard in self._shards:
            shard.close()


    def __enter__(self):
        return self


    def __exit__(self):
        self.close()


    def __len__(self):
        return sum(len(shard) for shard in self._shards)
